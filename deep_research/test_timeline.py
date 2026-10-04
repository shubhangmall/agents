"""Tests for the live research progress timeline (ux-01)."""
import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import research_manager
import timeline
from timeline import TimelineState, render_timeline, TIMELINE_MARKER


class TimelineRenderTests(unittest.TestCase):
    def _state(self):
        state = TimelineState(query="batteries")
        state.set_plan([("q1", "reason one"), ("q2", "reason two")])
        return state

    def test_every_render_is_prefixed_with_marker(self):
        state = TimelineState()
        self.assertTrue(render_timeline(state).startswith(TIMELINE_MARKER))
        self.assertTrue(render_timeline(self._state()).startswith(TIMELINE_MARKER))
        state.mark_done("2 searches")
        self.assertTrue(render_timeline(state).startswith(TIMELINE_MARKER))

    def test_query_and_reason_text_is_html_escaped(self):
        state = TimelineState()
        state.set_plan([('<script>alert("x")</script>', "<b>bold</b>")])
        html = render_timeline(state)
        self.assertNotIn("<script>", html)
        self.assertNotIn("<b>bold</b>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_plan_stage_lists_each_search_with_reason(self):
        html = render_timeline(self._state())
        self.assertIn("Research plan", html)
        self.assertIn("q1", html)
        self.assertIn("reason two", html)

    def test_search_progress_counts_completed(self):
        state = self._state()
        html = render_timeline(state)
        self.assertIn("0 of 2 searches complete", html)
        state.mark_search_done("q1", ok=True, meta="3 sources")
        html = render_timeline(state)
        self.assertIn("1 of 2 searches complete", html)
        self.assertIn("3 sources", html)

    def test_failed_search_is_marked_not_dropped(self):
        state = self._state()
        state.mark_search_done("q1", ok=False)
        html = render_timeline(state)
        self.assertIn("1 of 2 searches complete", html)
        self.assertIn("failed", html)

    def test_write_stage_shows_synthesizing_message(self):
        state = self._state()
        state.begin_writing()
        html = render_timeline(state)
        self.assertIn("Writing report", html)
        self.assertIn("Synthesizing", html)

    def test_done_state_is_a_collapsed_summary(self):
        state = self._state()
        state.mark_done("2 searches · 5 sources · 42s")
        html = render_timeline(state)
        self.assertIn("Research complete", html)
        self.assertIn("2 searches · 5 sources · 42s", html)
        # collapsed: no per-item checklist or stage boxes leak through
        self.assertNotIn("Research plan", html)
        self.assertNotIn("reason one", html)

    def test_planning_state_renders_before_plan_exists(self):
        state = TimelineState()
        state.begin_planning()
        html = render_timeline(state)
        self.assertTrue(html.startswith(TIMELINE_MARKER))
        self.assertIn("Planning searches", html)
        self.assertNotIn("Research plan", html)

    def test_failed_state_renders_collapsed_error(self):
        state = TimelineState()
        state.mark_failed("Planning failed")
        html = render_timeline(state)
        self.assertTrue(html.startswith(TIMELINE_MARKER))
        self.assertIn("Research failed", html)
        self.assertIn("Planning failed", html)
        self.assertNotIn('<span class="drt-spin">', html)
        self.assertNotIn("Research plan", html)

    def test_empty_plan_renders_without_crashing(self):
        state = TimelineState()
        state.set_plan([])
        html = render_timeline(state)
        self.assertTrue(html.startswith(TIMELINE_MARKER))
        state.mark_done("0 searches · 0 sources · 1s")
        self.assertIn("Research complete", render_timeline(state))


class TimelineOrchestrationTests(unittest.IsolatedAsyncioTestCase):
    async def _run_with_mocks(self, queries=("q1", "q2"), fail=()):
        manager = research_manager.ResearchManager()
        plan = SimpleNamespace(
            searches=[SimpleNamespace(query=q, reason="r") for q in queries]
        )

        async def fake_plan(query):
            return plan

        async def fake_search(item):
            await asyncio.sleep(0)
            if item.query in fail:
                raise RuntimeError("mock failure")
            return SimpleNamespace(query=item.query, sources=(1, 2, 3))

        async def fake_writer(query, results):
            yield "chunk1"
            yield "chunk2"

        with (
            patch.object(manager, "plan_searches", fake_plan),
            patch.object(research_manager, "search_web", fake_search),
            patch.object(manager, "write_report", fake_writer),
            patch.dict(os.environ, {"SEND_RESEARCH_EMAIL": ""}),
        ):
            return [chunk async for chunk in manager.run("query")]

    async def test_run_yields_timeline_progress_then_report(self):
        chunks = await self._run_with_mocks()
        markers = [c for c in chunks if c.startswith(TIMELINE_MARKER)]
        # planning + plan/searching + 2 search completions + writing + done
        self.assertEqual(len(markers), 6)
        self.assertIn("Planning searches", markers[0])
        self.assertNotIn("Research plan", markers[0])
        self.assertIn("Research plan", markers[1])
        self.assertIn("q1", markers[1])
        self.assertIn("0 of 2 searches complete", markers[1])
        self.assertIn("1 of 2 searches complete", markers[2])
        self.assertIn("2 of 2 searches complete", markers[3])
        self.assertIn("Writing report", markers[4])
        self.assertIn("Research complete", markers[5])
        self.assertIn("2 searches · 6 sources", markers[5])

    async def test_full_timeline_stage_sequence(self):
        """Prove the end-to-end stage order: Planning -> Searching -> Writing -> Done."""
        chunks = await self._run_with_mocks()
        markers = [c for c in chunks if c.startswith(TIMELINE_MARKER)]
        stages = []
        for marker in markers:
            if "Planning searches" in marker and "Research plan" not in marker:
                stages.append("planning")
            elif "Research complete" in marker and "Stage" not in marker:
                stages.append("done")
            elif "Synthesizing" in marker:
                stages.append("writing")
            elif "searches complete" in marker:
                stages.append("searching")
            else:
                stages.append("unknown")
        self.assertEqual(
            stages,
            ["planning", "searching", "searching", "searching", "writing", "done"],
        )

    async def test_planning_failure_yields_failed_timeline_then_raises(self):
        manager = research_manager.ResearchManager()

        async def boom(query):
            raise RuntimeError("mock planning failure")

        with patch.object(manager, "plan_searches", boom):
            chunks = []
            with self.assertRaises(RuntimeError):
                async for chunk in manager.run("query"):
                    chunks.append(chunk)
        self.assertEqual(len(chunks), 2)
        self.assertTrue(chunks[0].startswith(TIMELINE_MARKER))
        self.assertIn("Planning searches", chunks[0])
        self.assertTrue(chunks[1].startswith(TIMELINE_MARKER))
        self.assertIn("Research failed", chunks[1])
        # Collapsed failure bar: no spinner element left running.
        self.assertNotIn('<span class="drt-spin">', chunks[1])

    async def test_writer_failure_shows_failed_timeline_then_raises(self):
        """The Writing spinner must not remain stuck after a writer failure."""
        manager = research_manager.ResearchManager()
        plan = SimpleNamespace(searches=[SimpleNamespace(query="q", reason="r")])

        async def fake_plan(query):
            return plan

        async def fake_search(item):
            return SimpleNamespace(query=item.query, sources=(1,))

        async def failing_writer(query, results):
            yield "partial"
            raise RuntimeError("mock writer failure")

        with (
            patch.object(manager, "plan_searches", fake_plan),
            patch.object(research_manager, "search_web", fake_search),
            patch.object(manager, "write_report", failing_writer),
        ):
            chunks = []
            with self.assertRaises(RuntimeError):
                async for chunk in manager.run("query"):
                    chunks.append(chunk)
        markers = [c for c in chunks if c.startswith(TIMELINE_MARKER)]
        # planning + plan + 1 search completion + writing + failed
        self.assertEqual(len(markers), 5)
        # the writing spinner was shown while the writer was working...
        self.assertIn("Synthesizing", markers[3])
        self.assertIn('<span class="drt-spin">', markers[3])
        # ...and the terminal state carries no spinner.
        self.assertIn("Research failed", markers[4])
        self.assertNotIn('<span class="drt-spin">', markers[4])
        # partial report streamed before the failure, then the error propagated
        report_chunks = [c for c in chunks if not c.startswith(TIMELINE_MARKER)]
        self.assertEqual(report_chunks, ["partial"])

    async def test_run_preserves_final_report_contract(self):
        chunks = await self._run_with_mocks()
        self.assertEqual(chunks[-1], "Research complete!\n\nchunk1chunk2")
        # report chunks still stream as plain markdown between timeline updates
        report_chunks = [c for c in chunks if not c.startswith(TIMELINE_MARKER)]
        self.assertEqual(report_chunks, ["chunk1", "chunk1chunk2", "Research complete!\n\nchunk1chunk2"])

    async def test_failed_search_keeps_timeline_moving(self):
        chunks = await self._run_with_mocks(fail=("q1",))
        markers = [c for c in chunks if c.startswith(TIMELINE_MARKER)]
        self.assertEqual(len(markers), 6)
        self.assertIn("failed", markers[3])
        self.assertIn("2 of 2 searches complete", markers[3])
        self.assertTrue(chunks[-1].endswith("chunk1chunk2"))

    async def test_empty_plan_still_completes(self):
        chunks = await self._run_with_mocks(queries=())
        markers = [c for c in chunks if c.startswith(TIMELINE_MARKER)]
        self.assertEqual(len(markers), 4)  # planning + plan + writing + done
        self.assertIn("Planning searches", markers[0])
        self.assertTrue(chunks[-1].endswith("chunk1chunk2"))

    async def test_perform_searches_callback_fires_once_per_item(self):
        calls = []

        async def fake_search(item):
            await asyncio.sleep(0)
            if item.query == "bad":
                raise RuntimeError("mock failure")
            return SimpleNamespace(query=item.query, sources=(1,))

        plan = SimpleNamespace(
            searches=[SimpleNamespace(query=q) for q in ("one", "bad", "two")]
        )
        with patch.object(research_manager, "search_web", fake_search):
            results = await research_manager.ResearchManager().perform_searches(
                plan,
                on_search_done=lambda item, result, c, t: calls.append(
                    (item.query, result is not None, c, t)
                ),
            )
        self.assertEqual(sorted(r.query for r in results), ["one", "two"])
        self.assertEqual(len(calls), 3)
        self.assertEqual(sorted(c[0] for c in calls), ["bad", "one", "two"])
        self.assertTrue(all(c[3] == 3 for c in calls))
        by_query = {c[0]: c for c in calls}
        self.assertFalse(by_query["bad"][1])
        self.assertTrue(by_query["one"][1])


if __name__ == "__main__":
    unittest.main()
