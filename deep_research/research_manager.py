import asyncio
import logging
import os

from config import Settings
from email_agent import send_email
from planner_agent import WebSearchPlan, plan_searches
from provider_errors import ProviderError
from search_agent import SearchResult, search_web
from timeline import TimelineState, render_timeline
from writer_agent import stream_report


class ResearchManager:
    async def run(self, query: str, settings: Settings | None = None):
        """Run the research pipeline and yield progress/report chunks to Gradio.

        Progress updates are TimelineUpdate events (see timeline.py), routed by
        the UI to a dedicated progress component by type. Report chunks are
        plain strings and keep the original markdown contract; the final chunk
        is still "Research complete!\\n\\n" + the full report.

        settings defaults to Settings.from_env(); callers (e.g. the UI depth
        control) may pass per-run overrides instead.
        """
        settings = settings or Settings.from_env()
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
            self.perform_searches(search_plan, on_search_done=on_search_done, settings=settings)
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

    async def perform_searches(
        self,
        search_plan: WebSearchPlan,
        *,
        on_search_done=None,
        settings: Settings | None = None,
    ) -> list[SearchResult]:
        """Run the planned searches concurrently.

        on_search_done, when given, is called as on_search_done(item, result,
        completed, total) after every search; result is None when that search
        failed. It is always invoked exactly once per planned search.
        settings defaults to Settings.from_env() and is threaded through to
        search_web so per-run overrides (e.g. UI depth presets) take effect.
        """
        print("Searching...")
        settings = settings or Settings.from_env()

        async def run_one(item):
            try:
                return item, await search_web(item, settings)
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
