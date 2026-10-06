import asyncio
import logging
import os

from email_agent import send_email
from plan_preview import PlanReady
from planner_agent import WebSearchPlan, plan_searches
from provider_errors import ProviderError
from search_agent import SearchResult, search_web
from timeline import TimelineState, render_timeline
from writer_agent import stream_report


class ResearchManager:
    async def run(self, query: str):
        """Run the full research pipeline and yield progress/report chunks.

        Single-shot path (used by tests and non-interactive callers): runs
        plan_phase() and feeds the resulting plan straight into
        run_from_plan(). The outward chunk contract is unchanged — TimelineUpdate
        events and plain report strings; the PlanReady event is consumed
        internally and never yielded to the caller.
        """
        search_plan = None
        async for chunk in self.plan_phase(query):
            if isinstance(chunk, PlanReady):
                search_plan = chunk.plan
            else:
                yield chunk
        async for chunk in self.run_from_plan(query, search_plan):
            yield chunk

    async def plan_phase(self, query: str):
        """Stage 1 of the two-phase flow (ux-04): plan, then pause for approval.

        Yields TimelineUpdate progress events while planning, then exactly one
        PlanReady carrying the planner's WebSearchPlan. No searching starts
        here; the caller collects the plan, lets the user approve/edit/delete
        /regenerate it, and continues with run_from_plan(). A planner failure
        yields a terminal failed timeline and re-raises, same as run().
        """
        print("Starting research...")
        state = TimelineState(query=query)
        state.begin_planning()
        yield render_timeline(state)
        try:
            search_plan = await self.plan_searches(query)
        except Exception:
            # Don't leave a stuck "planning" spinner; the error still propagates
            # to the UI's error handling below.
            state.mark_failed("Planning failed")
            yield render_timeline(state)
            raise
        state.set_plan([(s.query, s.reason) for s in search_plan.searches])
        yield render_timeline(state)
        yield PlanReady(search_plan)

    async def run_from_plan(self, query: str, search_plan: WebSearchPlan):
        """Stage 2 of the two-phase flow (ux-04): execute an approved plan.

        Runs the searches, streams the report, and yields TimelineUpdate
        progress events plus plain report strings — the same chunk contract as
        the tail of run(). The plan shown in the timeline is the approved
        (possibly edited) one. Does not re-render the plan box first: the
        caller (plan_phase or the approval UI) already displayed it.
        """
        state = TimelineState(query=query)
        state.set_plan([(s.query, s.reason) for s in search_plan.searches])

        queue: asyncio.Queue = asyncio.Queue()

        def on_search_done(item, result, completed, total):
            meta = ""
            if result is not None:
                try:
                    meta = f"{len(result.sources)} sources"
                except Exception:
                    meta = ""
            state.mark_search_done(item.query, ok=result is not None, meta=meta)
            queue.put_nowait(render_timeline(state))

        search_task = asyncio.create_task(
            self.perform_searches(search_plan, on_search_done=on_search_done)
        )
        # perform_searches invokes on_search_done exactly once per planned
        # search before returning. Race the queue against the task itself so a
        # failed search phase surfaces its exception instead of hanging here.
        remaining = len(search_plan.searches)
        while remaining > 0:
            getter = asyncio.create_task(queue.get())
            done, pending = await asyncio.wait(
                {getter, search_task}, return_when=asyncio.FIRST_COMPLETED
            )
            if search_task in done:
                if getter in done:
                    # The getter already consumed a queued update; deliver it
                    # instead of dropping it.
                    yield getter.result()
                    remaining -= 1
                for p in pending:
                    p.cancel()
                # Re-raises if the search phase itself failed.
                search_results = search_task.result()
                while remaining > 0 and not queue.empty():
                    yield queue.get_nowait()
                    remaining -= 1
                break
            yield getter.result()
            remaining -= 1
        else:
            search_results = await search_task

        state.begin_writing()
        yield render_timeline(state)

        report_text = ""
        try:
            async for chunk in self.write_report(query, search_results):
                report_text += chunk
                yield report_text
        except Exception:
            # Don't leave a stuck "writing" spinner; the error still propagates
            # to the UI's error handling below.
            state.mark_failed("Writing failed")
            yield render_timeline(state)
            raise

        total_sources = sum(len(getattr(r, "sources", None) or []) for r in search_results)
        state.mark_done(
            f"{len(search_plan.searches)} searches · {total_sources} sources · {state.elapsed():.0f}s"
        )
        yield render_timeline(state)

        if os.getenv("SEND_RESEARCH_EMAIL", "").lower() in {"1", "true", "yes"}:
            try:
                send_email("Deep Research report", report_text)
            except Exception:
                logging.error("Optional research email failed")

        yield "Research complete!\n\n" + report_text

    async def plan_searches(self, query: str) -> WebSearchPlan:
        print("Planning searches...")
        plan = await plan_searches(query)
        print(f"Will perform {len(plan.searches)} searches")
        return plan

    async def perform_searches(self, search_plan: WebSearchPlan, *, on_search_done=None) -> list[SearchResult]:
        """Run the planned searches concurrently.

        on_search_done, when given, is called as on_search_done(item, result,
        completed, total) after every search; result is None when that search
        failed. It is always invoked exactly once per planned search.
        """
        print("Searching...")

        async def run_one(item):
            try:
                return item, await search_web(item)
            except ProviderError as error:
                print(f"Search failed: {error.category}")
                return item, None
            except Exception:
                print("Search failed: unexpected provider failure")
                return item, None

        tasks = [asyncio.create_task(run_one(item)) for item in search_plan.searches]
        results: list[SearchResult] = []
        completed = 0
        total = len(tasks)
        for coro in asyncio.as_completed(tasks):
            item, result = await coro
            if result is not None:
                results.append(result)
            completed += 1
            print(f"Searching... {completed}/{total} completed")
            if on_search_done is not None:
                on_search_done(item, result, completed, total)
        print("Finished searching")
        return results

    async def write_report(self, query: str, search_results: list[SearchResult]):
        print("Writing report...")
        async for chunk in stream_report(query, search_results):
            yield chunk
        print("Finished writing report")
