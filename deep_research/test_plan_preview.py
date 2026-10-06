"""Tests for the plan preview / approval flow (ux-04)."""
import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import plan_preview
import planner_agent
import research_manager
import timeline
from plan_preview import PlanReady, plan_to_rows, rows_to_plan
from planner_agent import HOW_MANY_SEARCHES, WebSearchItem, WebSearchPlan
from timeline import TimelineUpdate


def _plan(*queries):
    return WebSearchPlan(
        searches=[WebSearchItem(reason=f"reason {q}", query=q) for q in queries]
    )


class PlanRowTests(unittest.TestCase):
    def test_plan_to_rows_preserves_queries_reasons_and_order(self):
        rows = plan_to_rows(_plan("q1", "q2"))
        self.assertEqual(rows, [("q1", "reason q1"), ("q2", "reason q2")])

    def test_plan_to_rows_caps_at_planner_limit(self):
        rows = plan_to_rows(_plan(*[f"q{i}" for i in range(8)]))
        self.assertEqual(len(rows), HOW_MANY_SEARCHES)

    def test_rows_to_plan_round_trips_edited_queries(self):
        plan = rows_to_plan(["  edited one  ", "q2"])
        self.assertEqual([s.query for s in plan.searches], ["edited one", "q2"])

    def test_rows_to_plan_drops_blank_rows_as_delete(self):
        plan = rows_to_plan(["q1", "", "   ", None, "q2"])
        self.assertEqual([s.query for s in plan.searches], ["q1", "q2"])

    def test_rows_to_plan_caps_at_planner_limit(self):
        plan = rows_to_plan([f"q{i}" for i in range(8)])
        self.assertEqual(len(plan.searches), HOW_MANY_SEARCHES)

    def test_rows_to_plan_resets_stale_reasons(self):
        plan = rows_to_plan(["q1"])
        self.assertEqual(plan.searches[0].reason, "")

    def test_rows_to_plan_empty_rows_yield_empty_plan(self):
        self.assertEqual(rows_to_plan(["", "  "]).searches, [])
        self.assertEqual(rows_to_plan([]).searches, [])


class PlanPhaseTests(unittest.IsolatedAsyncioTestCase):
    async def _phase_with_mocks(self, queries=("q1", "q2")):
        manager = research_manager.ResearchManager()
        plan = SimpleNamespace(
            searches=[SimpleNamespace(query=q, reason="r") for q in queries]
        )

        async def fake_plan(query):
            return plan

        with patch.object(manager, "plan_searches", fake_plan):
            return [chunk async for chunk in manager.plan_phase("query")]

    async def test_plan_phase_yields_progress_then_exactly_one_plan_ready(self):
        chunks = await self._phase_with_mocks()
        updates = [c for c in chunks if isinstance(c, TimelineUpdate)]
        ready = [c for c in chunks if isinstance(c, PlanReady)]
        self.assertEqual(len(ready), 1)
        self.assertIs(chunks[-1], ready[0])  # PlanReady is always last
        self.assertEqual(len(updates), 2)  # planning spinner + plan set
        self.assertIn("Planning searches", updates[0].html)
        self.assertIn("Research plan", updates[1].html)

    async def test_plan_ready_carries_the_planner_output(self):
        chunks = await self._phase_with_mocks(("a", "b", "c"))
        ready = next(c for c in chunks if isinstance(c, PlanReady))
        self.assertEqual([s.query for s in ready.plan.searches], ["a", "b", "c"])

    async def test_plan_phase_starts_no_searches(self):
        with patch.object(
            research_manager, "search_web", side_effect=AssertionError("must not search")
        ):
            await self._phase_with_mocks()

    async def test_planning_failure_yields_failed_timeline_then_raises(self):
        manager = research_manager.ResearchManager()

        async def boom(query):
            raise RuntimeError("mock planning failure")

        with patch.object(manager, "plan_searches", boom):
            chunks = []
            with self.assertRaises(RuntimeError):
                async for chunk in manager.plan_phase("query"):
                    chunks.append(chunk)
        self.assertEqual(len(chunks), 2)
        self.assertIsInstance(chunks[0], TimelineUpdate)
        self.assertIn("Planning searches", chunks[0].html)
        self.assertIsInstance(chunks[1], TimelineUpdate)
        self.assertIn("Research failed", chunks[1].html)
        self.assertFalse(any(isinstance(c, PlanReady) for c in chunks))


class RunFromPlanTests(unittest.IsolatedAsyncioTestCase):
    async def _run_from_plan_with_mocks(self, queries=("q1", "q2")):
        manager = research_manager.ResearchManager()
        plan = _plan(*queries)

        async def fake_search(item):
            await asyncio.sleep(0)
            return SimpleNamespace(query=item.query, sources=(1, 2))

        async def fake_writer(query, results):
            yield "chunk1"

        with (
            patch.object(research_manager, "search_web", fake_search),
            patch.object(manager, "write_report", fake_writer),
            patch.dict(os.environ, {"SEND_RESEARCH_EMAIL": ""}),
        ):
            return [chunk async for chunk in manager.run_from_plan("query", plan)]

    async def test_run_from_plan_never_yields_plan_ready(self):
        chunks = await self._run_from_plan_with_mocks()
        self.assertFalse(any(isinstance(c, PlanReady) for c in chunks))

    async def test_run_from_plan_searches_writes_and_completes(self):
        chunks = await self._run_from_plan_with_mocks()
        markers = [c for c in chunks if isinstance(c, TimelineUpdate)]
        # 2 search completions + writing + done (the plan box was already
        # rendered by plan_phase, so it is not re-rendered here)
        self.assertEqual(len(markers), 4)
        self.assertIn("1 of 2 searches complete", markers[0].html)
        self.assertIn("2 of 2 searches complete", markers[1].html)
        self.assertIn("Writing report", markers[2].html)
        self.assertIn("Research complete", markers[3].html)
        self.assertIn("2 searches · 4 sources", markers[3].html)
        self.assertEqual(chunks[-1], "Research complete!\n\nchunk1")

    async def test_run_from_plan_uses_the_approved_edited_plan(self):
        manager = research_manager.ResearchManager()
        seen = []

        async def fake_search(item):
            seen.append(item.query)
            return SimpleNamespace(query=item.query, sources=())

        async def fake_writer(query, results):
            yield "done"

        approved = rows_to_plan(["edited query", "", "third"])
        with (
            patch.object(research_manager, "search_web", fake_search),
            patch.object(manager, "write_report", fake_writer),
            patch.dict(os.environ, {"SEND_RESEARCH_EMAIL": ""}),
        ):
            chunks = [chunk async for chunk in manager.run_from_plan("query", approved)]
        self.assertEqual(sorted(seen), ["edited query", "third"])
        done = next(c for c in chunks if isinstance(c, TimelineUpdate) and "Research complete" in c.html)
        self.assertIn("2 searches", done.html)

    async def test_single_shot_run_keeps_its_chunk_contract(self):
        """run() = plan_phase + run_from_plan; PlanReady never leaks out and
        the outward sequence is unchanged."""
        manager = research_manager.ResearchManager()
        plan = SimpleNamespace(
            searches=[SimpleNamespace(query=q, reason="r") for q in ("q1", "q2")]
        )

        async def fake_plan(query):
            return plan

        async def fake_search(item):
            await asyncio.sleep(0)
            return SimpleNamespace(query=item.query, sources=(1,))

        async def fake_writer(query, results):
            yield "chunk1"

        with (
            patch.object(manager, "plan_searches", fake_plan),
            patch.object(research_manager, "search_web", fake_search),
            patch.object(manager, "write_report", fake_writer),
            patch.dict(os.environ, {"SEND_RESEARCH_EMAIL": ""}),
        ):
            chunks = [chunk async for chunk in manager.run("query")]
        self.assertFalse(any(isinstance(c, PlanReady) for c in chunks))
        markers = [c for c in chunks if isinstance(c, TimelineUpdate)]
        self.assertEqual(len(markers), 6)  # planning + plan + 2 searches + writing + done
        self.assertEqual(chunks[-1], "Research complete!\n\nchunk1")


class PlanChunkRoutingTests(unittest.TestCase):
    def test_plan_ready_is_dropped_by_route_chunk(self):
        """PlanReady must never reach the raw-HTML timeline component via
        route_chunk; the UI routes it by type instead."""
        t, r, emit = timeline.route_chunk(PlanReady(_plan("q1")), "<b>t</b>", "md")
        self.assertEqual((t, r, emit), ("<b>t</b>", "md", False))

    def test_plan_preview_imports_without_gradio(self):
        self.assertTrue(hasattr(plan_preview, "PlanReady"))


def _import_deep_research_ui():
    """Import deep_research with the module-level ui.launch() stubbed out.

    deep_research builds its Gradio UI at import time; stubbing launch keeps
    the import side-effect free so the UI handler functions are testable.
    """
    import gradio as gr
    from unittest.mock import patch

    patcher = patch.object(gr.Blocks, "launch", return_value=None)
    patcher.start()
    try:
        import deep_research

        return deep_research
    finally:
        patcher.stop()


class ApproveAndRunUITests(unittest.IsolatedAsyncioTestCase):
    """Regression tests for the ux-04 review fixes in deep_research.py."""

    @classmethod
    def setUpClass(cls):
        cls.dr = _import_deep_research_ui()

    async def test_empty_plan_keeps_rows_visible(self):
        """Fix 1: approving an empty plan must leave the textboxes visible
        (empty) so the user can type a search back in — not a dead accordion."""
        chunks = [c async for c in self.dr.approve_and_run("q", "", "", "", "", "")]
        self.assertEqual(len(chunks), 1)
        yielded = chunks[0]
        # (timeline, report, accordion, *5 rows)
        self.assertEqual(len(yielded), 8)
        self.assertTrue(yielded[2]["visible"])  # accordion stays visible
        for row_update in yielded[3:]:
            self.assertTrue(row_update["visible"])
            self.assertEqual(row_update["value"], "")

    async def test_empty_plan_warns_to_restore_or_regenerate(self):
        chunks = [c async for c in self.dr.approve_and_run("q", "", "  ", None, "", "")]
        self.assertEqual(len(chunks), 1)
        self.assertIn("No searches left in the plan", chunks[0][1])

    async def test_approve_and_run_uses_planned_query_snapshot(self):
        """Fix 3: the run must use the snapshotted planned query, never the
        live query box value passed at click time."""
        seen = {}

        async def fake_run_from_plan(self, query, plan):
            seen["query"] = query
            return
            yield  # make this an async generator

        with patch.object(
            self.dr.ResearchManager, "run_from_plan", fake_run_from_plan
        ):
            chunks = [
                c
                async for c in self.dr.approve_and_run(
                    "planned query", "search one", "", "", "", ""
                )
            ]
        self.assertEqual(seen["query"], "planned query")
        self.assertEqual(chunks, [])  # no chunks from the empty fake pipeline

    async def test_plan_yields_planned_query_snapshot(self):
        """Fix 3: plan() snapshots the query it planned for as the trailing
        yield item, feeding the gr.State the approve step reads."""
        plan = _plan("q1", "q2")

        async def fake_plan_phase(self, query):
            yield PlanReady(plan)

        with patch.object(
            self.dr.ResearchManager, "plan_phase", fake_plan_phase
        ):
            chunks = [c async for c in self.dr.plan("my query")]
        self.assertTrue(chunks)
        # trailing item of every plan() yield is the snapshotted query
        for chunk in chunks:
            self.assertEqual(chunk[-1], "my query")
        # the plan-ready yield shows the accordion with the planned rows
        ready = chunks[-1]
        self.assertTrue(ready[2]["visible"])
        self.assertEqual(ready[3]["value"], "q1")


if __name__ == "__main__":
    unittest.main()
