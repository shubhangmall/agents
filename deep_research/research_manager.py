import asyncio
import os

from email_agent import send_email
from planner_agent import WebSearchPlan, plan_searches
from search_agent import SearchResult, search_web
from writer_agent import stream_report


class ResearchManager:
    async def run(self, query: str):
        """Run the research pipeline and yield progress/report text to Gradio."""
        print("Starting research...")
        search_plan = await self.plan_searches(query)
        yield "Searches planned, starting to search..."

        search_results = await self.perform_searches(search_plan)
        yield "Searches complete, writing report..."

        report_text = ""
        async for chunk in self.write_report(query, search_results):
            report_text += chunk
            yield report_text

        if os.getenv("SEND_RESEARCH_EMAIL", "").lower() in {"1", "true", "yes"}:
            send_email("Deep Research report", report_text)

        yield "Research complete!\n\n" + report_text

    async def plan_searches(self, query: str) -> WebSearchPlan:
        print("Planning searches...")
        plan = await plan_searches(query)
        print(f"Will perform {len(plan.searches)} searches")
        return plan

    async def perform_searches(self, search_plan: WebSearchPlan) -> list[SearchResult]:
        print("Searching...")
        tasks = [asyncio.create_task(search_web(item)) for item in search_plan.searches]
        results: list[SearchResult] = []
        completed = 0
        for task in asyncio.as_completed(tasks):
            try:
                results.append(await task)
            except Exception as error:
                print(f"Search failed: {error}")
            completed += 1
            print(f"Searching... {completed}/{len(tasks)} completed")
        print("Finished searching")
        return results

    async def write_report(self, query: str, search_results: list[SearchResult]):
        print("Writing report...")
        async for chunk in stream_report(query, search_results):
            yield chunk
        print("Finished writing report")
