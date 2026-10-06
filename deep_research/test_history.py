"""Tests for session history persistence (ux-10)."""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import history
import research_manager


def _source(url, title="t", domain="d"):
    return SimpleNamespace(url=url, title=title, domain=domain)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = str(Path(self.tmp.name) / "history.json")

    def _sources(self):
        return [{"title": "t", "url": "https://example.com/a", "domain": "example.com"}]

    def test_load_missing_file_returns_empty(self):
        self.assertEqual(history.load_history(path=self.path), [])

    def test_load_corrupt_file_returns_empty(self):
        Path(self.path).write_text("not json{{{", encoding="utf-8")
        self.assertEqual(history.load_history(path=self.path), [])

    def test_load_wrong_shape_returns_empty(self):
        for payload in ('{"runs": "nope"}', '{"other": []}', "[1, 2]"):
            Path(self.path).write_text(payload, encoding="utf-8")
            self.assertEqual(history.load_history(path=self.path), [])

    def test_append_and_load_roundtrip(self):
        entry = history.append_run(
            "quantum batteries",
            "# Report\n\nbody",
            self._sources(),
            path=self.path,
            timestamp=1720000000.0,
        )
        self.assertTrue(entry["id"])
        self.assertEqual(entry["query"], "quantum batteries")
        self.assertEqual(entry["report"], "# Report\n\nbody")
        self.assertEqual(entry["timestamp"], 1720000000.0)
        self.assertEqual(entry["sources"], self._sources())
        loaded = history.load_history(path=self.path)
        self.assertEqual(loaded, [entry])

    def test_load_returns_newest_first(self):
        history.append_run("first", "r1", [], path=self.path, timestamp=100.0)
        history.append_run("second", "r2", [], path=self.path, timestamp=200.0)
        loaded = history.load_history(path=self.path)
        self.assertEqual([e["query"] for e in loaded], ["second", "first"])

    def test_append_trims_oldest_beyond_max_entries(self):
        for i in range(5):
            history.append_run(f"q{i}", "r", [], path=self.path,
                               timestamp=float(i), max_entries=3)
        loaded = history.load_history(path=self.path)
        self.assertEqual([e["query"] for e in loaded], ["q4", "q3", "q2"])

    def test_delete_run_removes_entry(self):
        keep = history.append_run("keep", "r", [], path=self.path)
        drop = history.append_run("drop", "r", [], path=self.path)
        self.assertTrue(history.delete_run(drop["id"], path=self.path))
        loaded = history.load_history(path=self.path)
        self.assertEqual([e["id"] for e in loaded], [keep["id"]])

    def test_delete_unknown_id_returns_false(self):
        self.assertFalse(history.delete_run("nope", path=self.path))

    def test_entry_sources_malformed_entries_are_skipped(self):
        entry = history.append_run("q", "r", ["nope", {"url": "u"}], path=self.path)
        self.assertEqual(entry["sources"], [{"title": "", "url": "u", "domain": ""}])


class EntrySourcesTests(unittest.TestCase):
    def test_flattens_and_dedupes_by_url(self):
        results = [
            SimpleNamespace(sources=(
                _source("https://a.com/1", "A", "a.com"),
                _source("https://a.com/1", "A again", "a.com"),
            )),
            SimpleNamespace(sources=(_source("https://b.com/2", "B", "b.com"),)),
        ]
        self.assertEqual(
            history.entry_sources(results),
            [
                {"title": "A", "url": "https://a.com/1", "domain": "a.com"},
                {"title": "B", "url": "https://b.com/2", "domain": "b.com"},
            ],
        )

    def test_empty_results_yield_empty_sources(self):
        self.assertEqual(history.entry_sources([]), [])
        self.assertEqual(history.entry_sources(None), [])


class EntryLabelTests(unittest.TestCase):
    def test_label_contains_date_and_query(self):
        label = history.entry_label({"timestamp": 1720000000.0, "query": "batteries"})
        expected_when = time.strftime("%b %d, %Y · %H:%M", time.localtime(1720000000.0))
        self.assertEqual(label, f"{expected_when} · batteries")

    def test_long_query_is_truncated(self):
        label = history.entry_label({"timestamp": 1.0, "query": "x" * 100})
        self.assertTrue(label.endswith("x" * 59 + "…"))

    def test_empty_query_gives_date_only(self):
        label = history.entry_label({"timestamp": 1.0, "query": ""})
        self.assertEqual(label, time.strftime("%b %d, %Y · %H:%M", time.localtime(1.0)))


class PathConfigTests(unittest.TestCase):
    def test_env_override(self):
        with patch.dict(os.environ, {history.ENV_PATH: "~/custom-history.json"}):
            self.assertEqual(
                history.default_history_path(), Path.home() / "custom-history.json"
            )

    def test_default_path_is_home_json(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(history.ENV_PATH, None)
            self.assertEqual(
                history.default_history_path(), Path.home() / history.DEFAULT_FILENAME
            )


class ManagerHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def _run_with_mocks(self, manager):
        plan = SimpleNamespace(searches=[])

        async def fake_plan(query):
            return plan

        async def fake_writer(query, results):
            yield "complete report"

        with (
            patch.object(manager, "plan_searches", fake_plan),
            patch.object(manager, "write_report", fake_writer),
            patch.dict(os.environ, {"SEND_RESEARCH_EMAIL": ""}),
        ):
            return [chunk async for chunk in manager.run("test query")]

    async def test_run_persists_completed_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "history.json")
            manager = research_manager.ResearchManager(history_path=path)
            chunks = await self._run_with_mocks(manager)
            self.assertTrue(chunks[-1].endswith("complete report"))
            loaded = history.load_history(path=path)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0]["query"], "test query")
            self.assertEqual(loaded[0]["report"], "complete report")
            self.assertIn("timestamp", loaded[0])

    async def test_run_persists_sources_from_search_results(self):
        async def fake_search(item):
            return SimpleNamespace(
                query=item.query,
                sources=(_source("https://a.com/1", "A", "a.com"),),
            )

        plan = SimpleNamespace(searches=[SimpleNamespace(query="q1", reason="r1")])

        async def fake_plan(query):
            return plan

        async def fake_writer(query, results):
            yield "done"

        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "history.json")
            manager = research_manager.ResearchManager(history_path=path)
            with (
                patch.object(manager, "plan_searches", fake_plan),
                patch.object(manager, "write_report", fake_writer),
                patch.object(research_manager, "search_web", fake_search),
                patch.object(research_manager, "print"),
                patch.dict(os.environ, {"SEND_RESEARCH_EMAIL": ""}),
            ):
                _ = [chunk async for chunk in manager.run("q")]
            loaded = history.load_history(path=path)
            self.assertEqual(
                loaded[0]["sources"],
                [{"title": "A", "url": "https://a.com/1", "domain": "a.com"}],
            )

    async def test_run_without_history_path_does_not_persist(self):
        manager = research_manager.ResearchManager()
        with patch.object(history, "append_run") as append:
            await self._run_with_mocks(manager)
        append.assert_not_called()

    async def test_history_failure_does_not_break_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "history.json")
            manager = research_manager.ResearchManager(history_path=path)
            with patch.object(history, "append_run", side_effect=RuntimeError("disk")):
                chunks = await self._run_with_mocks(manager)
            self.assertTrue(chunks[-1].endswith("complete report"))


if __name__ == "__main__":
    unittest.main()
