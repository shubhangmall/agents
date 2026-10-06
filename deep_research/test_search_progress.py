"""Tests for per-search progress, elapsed timer, and cancel (ux-08)."""
import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import research_manager
import timeline
from timeline import (
    SearchProgress,
    TimelineState,
    TimelineUpdate,
    render_stopped,
    render_timeline,
)


class SearchProgressRenderTests(unittest.TestCase):
    def _state(self):
        state = TimelineState(query="batteries")
        state.set_plan([("q1", "reason one"), ("q2", "reason two")])
        return state

    def test_search_progress_event_carries_counts(self):
        event = SearchProgress(completed=2, total=5)
        self.assertEqual((event.completed, event.total), (2, 5))

    def test_search_box_shows_searching_n_of_m_with_elapsed(self):
        html = render_timeline(self._state()).html
        self.assertIn("Searching 0/2", html)
        self.assertIn("elapsed", html)

    def test_search_box_updates_count_and_elapsed_per_completion(self):
        state = self._state()
        state.mark_search_done("q1", ok=True, meta="3 sources")
        html = render_timeline(state).html
        self.assertIn("Searching 1/2", html)
        self.assertIn("s elapsed", html)
        self.assertNotIn("0/2", html)

    def test_search_box_shows_complete_count_when_finished(self):
        state = self._state()
        state.mark_search_done("q1", ok=True)
        state.mark_search_done("q2", ok=True)
        html = render_timeline(state).html
        self.assertIn("2/2 searches complete", html)
        self.assertIn("s elapsed", html)

    def test_stopped_state_renders_neutral_banner(self):
        state = self._state()
        state.mark_stopped()
        html = render_timeline(state).html
        self.assertIsInstance(render_timeline(state), TimelineUpdate)
        self.assertIn("Research stopped", html)
        self.assertIn("Stopped by user", html)
        # terminal: no spinner left running, collapsed like the failed bar
        self.assertNotIn('<span class="drt-spin">', html)
        self.assertNotIn("Research plan", html)

    def test_stopped_message_is_html_escaped(self):
        state = TimelineState()
        state.mark_stopped('<script>alert("x")</script>')
        html = render_timeline(state).html
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_render_stopped_helper_returns_banner_html(self):
        html = render_stopped()
        self.assertIsInstance(html, str)
        self.assertIn("Research stopped", html)
        self.assertNotIn('<span class="drt-spin">', html)

    def test_search_progress_is_never_routed_to_html(self):
        # The Gradio wrapper routes SearchProgress to gr.Progress before
        # route_chunk; route_chunk itself must not send it to the raw-HTML
        # timeline component.
        t, r, emit = timeline.route_chunk(
            SearchProgress(completed=1, total=2), "<b>t</b>", "md"
        )
        self.assertEqual((t, r, emit), ("<b>t</b>", "md", False))


class SearchProgressOrchestrationTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_run_yields_search_progress_per_completion(self):
        chunks = await self._run_with_mocks()
        progress = [c for c in chunks if isinstance(c, SearchProgress)]
        self.assertEqual(
            [(p.completed, p.total) for p in progress], [(1, 2), (2, 2)]
        )

    async def test_search_progress_interleaves_with_timeline_updates(self):
        chunks = await self._run_with_mocks()
        kinds = [
            "progress"
            if isinstance(c, SearchProgress)
            else "timeline"
            if isinstance(c, TimelineUpdate)
            else "report"
            for c in chunks
        ]
        # planning, plan, (timeline, progress) x2, writing, report chunks,
        # done timeline, final report string
        self.assertEqual(
            kinds,
            [
                "timeline", "timeline",
                "timeline", "progress",
                "timeline", "progress",
                "timeline",
                "report", "report",
                "timeline",
                "report",
            ],
        )

    async def test_failed_search_still_advances_progress(self):
        chunks = await self._run_with_mocks(fail=("q1",))
        progress = [c for c in chunks if isinstance(c, SearchProgress)]
        self.assertEqual(
            [(p.completed, p.total) for p in progress], [(1, 2), (2, 2)]
        )

    async def test_cancel_perform_searches_cancels_inflight_tasks(self):
        """Stop-button path: cancelling perform_searches must not orphan searches."""
        release = asyncio.Event()
        seen = []

        async def fake_search(item):
            seen.append(asyncio.current_task())
            await release.wait()  # block until the test releases/cancels
            return SimpleNamespace(query=item.query, sources=(1,))

        plan = SimpleNamespace(
            searches=[SimpleNamespace(query="q1"), SimpleNamespace(query="q2")]
        )
        manager = research_manager.ResearchManager()
        with patch.object(research_manager, "search_web", fake_search):
            task = asyncio.create_task(manager.perform_searches(plan))
            for _ in range(200):
                if len(seen) == 2:
                    break
                await asyncio.sleep(0.01)
            self.assertEqual(len(seen), 2)  # both searches in flight
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            # let the loop reap the cancelled children, then assert none linger
            await asyncio.gather(*seen, return_exceptions=True)
            for child in seen:
                self.assertTrue(child.done())
                self.assertTrue(child.cancelled())

    async def test_aclose_mid_search_cancels_inflight_searches(self):
        """Gradio Stop cancels the UI event; aclose() must stop the searches.

        Mirrors deep_research.run(): the event task is cancelled, the wrapper
        catches CancelledError and acloses the pipeline generator.
        """
        release = asyncio.Event()
        seen = []

        async def fake_search(item):
            seen.append(asyncio.current_task())
            await release.wait()
            return SimpleNamespace(query=item.query, sources=(1,))

        async def fake_plan(query):
            return SimpleNamespace(
                searches=[SimpleNamespace(query="q1", reason="r"),
                          SimpleNamespace(query="q2", reason="r")]
            )

        async def fake_writer(query, results):
            yield "chunk"

        manager = research_manager.ResearchManager()

        async def wrapper():
            agen = manager.run("query")
            try:
                async for _chunk in agen:
                    pass
            except asyncio.CancelledError:
                await agen.aclose()
                raise

        with (
            patch.object(manager, "plan_searches", fake_plan),
            patch.object(research_manager, "search_web", fake_search),
            patch.object(manager, "write_report", fake_writer),
            patch.dict(os.environ, {"SEND_RESEARCH_EMAIL": ""}),
        ):
            wrapper_task = asyncio.create_task(wrapper())
            for _ in range(200):
                if len(seen) == 2:
                    break
                await asyncio.sleep(0.01)
            self.assertEqual(len(seen), 2)  # both searches in flight
            wrapper_task.cancel()  # what Gradio does on Stop
            with self.assertRaises(asyncio.CancelledError):
                await wrapper_task
            # let the loop reap the cancelled children, then assert none linger
            await asyncio.gather(*seen, return_exceptions=True)
            for child in seen:
                self.assertTrue(child.done())
                self.assertTrue(child.cancelled())

    async def test_progress_events_do_not_disturb_report_contract(self):
        chunks = await self._run_with_mocks()
        self.assertEqual(chunks[-1], "Research complete!\n\nchunk1chunk2")
        report_chunks = [c for c in chunks if isinstance(c, str)]
        self.assertEqual(
            report_chunks, ["chunk1", "chunk1chunk2", "Research complete!\n\nchunk1chunk2"]
        )


if __name__ == "__main__":
    unittest.main()
