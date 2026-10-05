"""Tests for the live research progress timeline (ux-01)."""
import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import research_manager
import timeline
from timeline import TimelineState, TimelineUpdate, render_timeline


def _markers(chunks):
    return [c for c in chunks if isinstance(c, TimelineUpdate)]


def _html(chunk):
    return chunk.html if isinstance(chunk, TimelineUpdate) else chunk


class TimelineRenderTests(unittest.TestCase):
    def _state(self):
        state = TimelineState(query="batteries")
        state.set_plan([("q1", "reason one"), ("q2", "reason two")])
        return state

    def test_every_render_returns_a_typed_update(self):
        state = TimelineState()
        self.assertIsInstance(render_timeline(state), TimelineUpdate)
        self.assertIsInstance(render_timeline(self._state()), TimelineUpdate)
        state.mark_done("2 searches")
        self.assertIsInstance(render_timeline(state), TimelineUpdate)

    def test_query_and_reason_text_is_html_escaped(self):
        state = TimelineState()
        state.set_plan([('<script>alert("x")</script>', "<b>bold</b>")])
        html = render_timeline(state).html
        self.assertNotIn("<script>", html)
        self.assertNotIn("<b>bold</b>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_plan_stage_lists_each_search_with_reason(self):
        html = render_timeline(self._state()).html
        self.assertIn("Research plan", html)
        self.assertIn("q1", html)
        self.assertIn("reason two", html)

    def test_search_progress_counts_completed(self):
        state = self._state()
        html = render_timeline(state).html
        self.assertIn("0 of 2 searches complete", html)
        state.mark_search_done("q1", ok=True, meta="3 sources")
        html = render_timeline(state).html
        self.assertIn("1 of 2 searches complete", html)
        self.assertIn("3 sources", html)

    def test_failed_search_is_marked_not_dropped(self):
        state = self._state()
        state.mark_search_done("q1", ok=False)
        html = render_timeline(state).html
        self.assertIn("1 of 2 searches complete", html)
        self.assertIn("failed", html)

    def test_write_stage_shows_synthesizing_message(self):
        state = self._state()
        state.begin_writing()
        html = render_timeline(state).html
        self.assertIn("Writing report", html)
        self.assertIn("Synthesizing", html)

    def test_done_state_is_a_collapsed_summary(self):
        state = self._state()
        state.mark_done("2 searches · 5 sources · 42s")
        html = render_timeline(state).html
        self.assertIn("Research complete", html)
        self.assertIn("2 searches · 5 sources · 42s", html)
        # collapsed: no per-item checklist or stage boxes leak through
        self.assertNotIn("Research plan", html)
        self.assertNotIn("reason one", html)

    def test_planning_state_renders_before_plan_exists(self):
        state = TimelineState()
        state.begin_planning()
        html = render_timeline(state).html
        self.assertIn("Planning searches", html)
        self.assertNotIn("Research plan", html)

    def test_failed_state_renders_collapsed_error(self):
        state = TimelineState()
        state.mark_failed("Planning failed")
        html = render_timeline(state).html
        self.assertIn("Research failed", html)
        self.assertIn("Planning failed", html)
        self.assertNotIn('<span class="drt-spin">', html)
        self.assertNotIn("Research plan", html)

    def test_empty_plan_renders_without_crashing(self):
        state = TimelineState()
        state.set_plan([])
        html = render_timeline(state).html
        state.mark_done("0 searches · 0 sources · 1s")
        self.assertIn("Research complete", render_timeline(state).html)


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
        markers = _markers(chunks)
        # planning + plan/searching + 2 search completions + writing + done
        self.assertEqual(len(markers), 6)
        self.assertIn("Planning searches", _html(markers[0]))
        self.assertNotIn("Research plan", _html(markers[0]))
        self.assertIn("Research plan", _html(markers[1]))
        self.assertIn("q1", _html(markers[1]))
        self.assertIn("0 of 2 searches complete", _html(markers[1]))
        self.assertIn("1 of 2 searches complete", _html(markers[2]))
        self.assertIn("2 of 2 searches complete", _html(markers[3]))
        self.assertIn("Writing report", _html(markers[4]))
        self.assertIn("Research complete", _html(markers[5]))
        self.assertIn("2 searches · 6 sources", _html(markers[5]))

    async def test_full_timeline_stage_sequence(self):
        """Prove the end-to-end stage order: Planning -> Searching -> Writing -> Done."""
        chunks = await self._run_with_mocks()
        markers = _markers(chunks)
        stages = []
        for marker in markers:
            text = _html(marker)
            if "Planning searches" in text and "Research plan" not in text:
                stages.append("planning")
            elif "Research complete" in text and "Stage" not in text:
                stages.append("done")
            elif "Synthesizing" in text:
                stages.append("writing")
            elif "searches complete" in text:
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
        self.assertIsInstance(chunks[0], TimelineUpdate)
        self.assertIn("Planning searches", _html(chunks[0]))
        self.assertIsInstance(chunks[1], TimelineUpdate)
        self.assertIn("Research failed", _html(chunks[1]))
        # Collapsed failure bar: no spinner element left running.
        self.assertNotIn('<span class="drt-spin">', _html(chunks[1]))

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
        markers = _markers(chunks)
        # planning + plan + 1 search completion + writing + failed
        self.assertEqual(len(markers), 5)
        # the writing spinner was shown while the writer was working...
        self.assertIn("Synthesizing", _html(markers[3]))
        self.assertIn('<span class="drt-spin">', _html(markers[3]))
        # ...and the terminal state carries no spinner.
        self.assertIn("Research failed", _html(markers[4]))
        self.assertNotIn('<span class="drt-spin">', _html(markers[4]))
        # partial report streamed before the failure, then the error propagated
        report_chunks = [c for c in chunks if isinstance(c, str)]
        self.assertEqual(report_chunks, ["partial"])

    async def test_run_preserves_final_report_contract(self):
        chunks = await self._run_with_mocks()
        self.assertEqual(chunks[-1], "Research complete!\n\nchunk1chunk2")
        # report chunks still stream as plain markdown between timeline updates
        report_chunks = [c for c in chunks if isinstance(c, str)]
        self.assertEqual(report_chunks, ["chunk1", "chunk1chunk2", "Research complete!\n\nchunk1chunk2"])

    async def test_failed_search_keeps_timeline_moving(self):
        chunks = await self._run_with_mocks(fail=("q1",))
        markers = _markers(chunks)
        self.assertEqual(len(markers), 6)
        self.assertIn("failed", _html(markers[3]))
        self.assertIn("2 of 2 searches complete", _html(markers[3]))
        self.assertTrue(chunks[-1].endswith("chunk1chunk2"))

    async def test_empty_plan_still_completes(self):
        chunks = await self._run_with_mocks(queries=())
        markers = _markers(chunks)
        self.assertEqual(len(markers), 4)  # planning + plan + writing + done
        self.assertIn("Planning searches", _html(markers[0]))
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


class ChunkRoutingTests(unittest.TestCase):
    """Blocker 2: the timeline/report routing boundary.

    Routing is by chunk *type* (timeline.route_chunk, the exact function the
    Gradio wrapper uses), so model-generated report text can never be
    misrouted into the raw-HTML timeline component.
    """

    def test_timeline_update_routes_to_timeline_html(self):
        t, r, emit = timeline.route_chunk(TimelineUpdate("<b>x</b>"), "", "")
        self.assertEqual((t, r, emit), ("<b>x</b>", "", True))

    def test_report_str_routes_to_report_md(self):
        t, r, emit = timeline.route_chunk("hello", "<b>x</b>", "")
        self.assertEqual((t, r, emit), ("<b>x</b>", "hello", True))

    def test_marker_like_report_text_never_reaches_timeline_html(self):
        payload = "<!--ux-timeline--><img src=x onerror=alert(1)>"
        before = "<b>timeline</b>"
        t, r, emit = timeline.route_chunk(f"# Report\n\n{payload}", before, "")
        self.assertTrue(emit)
        self.assertEqual(t, before)  # timeline component untouched
        self.assertIn(payload, r)  # payload stays in markdown

    def test_unknown_chunk_types_are_dropped(self):
        t, r, emit = timeline.route_chunk({"x": 1}, "<b>t</b>", "md")
        self.assertEqual((t, r, emit), ("<b>t</b>", "md", False))
