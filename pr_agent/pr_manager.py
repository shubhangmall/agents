import json

from agents import Runner

from fix_agent import fix_agent
from github_client import GitHubClient
from models import BabysitReport, Issue, PRContext, ProposedFix, TriageResult
from reporter_agent import reporter_agent
from triage_agent import triage_agent

MAX_FIXES = 5


class PRManager:
    def __init__(self) -> None:
        self.github = GitHubClient()
        self._last_report_markdown: str | None = None
        self._last_pr_url: str | None = None

    @property
    def last_report_markdown(self) -> str | None:
        return self._last_report_markdown

    @property
    def last_pr_url(self) -> str | None:
        return self._last_pr_url

    async def run(self, pr_url: str):
        """Run the PR babysit process, yielding status updates and the final report."""
        self._last_pr_url = pr_url.strip()
        self._last_report_markdown = None

        yield "Fetching PR context..."
        context = await self.github.fetch(self._last_pr_url)

        yield "Triaging issues..."
        triage = await self.triage(context)
        actionable = triage.actionable_issues
        yield f"Found {len(triage.issues)} issue(s), {len(actionable)} actionable."

        fixes: list[ProposedFix] = []
        for issue in actionable[:MAX_FIXES]:
            summary_preview = issue.summary[:60]
            if len(issue.summary) > 60:
                summary_preview += "..."
            yield f"Proposing fix for: {summary_preview}"
            fix = await self.propose_fix(issue, context)
            fixes.append(fix)

        yield "Writing report..."
        report = await self.report(triage, fixes)
        self._last_report_markdown = report.markdown

        yield "Analysis complete!"
        yield report.markdown

    async def triage(self, context: PRContext) -> TriageResult:
        result = await Runner.run(
            triage_agent,
            context.to_prompt(),
        )
        return result.final_output_as(TriageResult)

    async def propose_fix(self, issue: Issue, context: PRContext) -> ProposedFix:
        file_context = await self._gather_file_context(issue, context)
        input_text = (
            f"Issue:\n{issue.model_dump_json(indent=2)}\n\n"
            f"PR diff (relevant excerpt):\n{self._relevant_diff(context, issue)}\n\n"
            f"File context:\n{file_context}"
        )
        result = await Runner.run(fix_agent, input_text)
        fix = result.final_output_as(ProposedFix)
        fix.issue_id = issue.id
        return fix

    async def report(
        self, triage: TriageResult, fixes: list[ProposedFix]
    ) -> BabysitReport:
        input_text = (
            f"Triage result:\n{triage.model_dump_json(indent=2)}\n\n"
            f"Proposed fixes:\n{json.dumps([f.model_dump() for f in fixes], indent=2)}"
        )
        result = await Runner.run(reporter_agent, input_text)
        return result.final_output_as(BabysitReport)

    async def post_comment(self) -> str:
        if not self._last_report_markdown or not self._last_pr_url:
            raise RuntimeError("No report available. Run analysis first.")
        await self.github.post_comment(self._last_pr_url, self._last_report_markdown)
        return "Comment posted successfully."

    async def _gather_file_context(self, issue: Issue, context: PRContext) -> str:
        paths = issue.related_files or [f.path for f in context.files]
        if not paths:
            return "(no file context available)"

        snippets: list[str] = []
        for path in paths[:3]:
            content = await self.github.fetch_file_content(
                context.url, path, context.head_ref
            )
            if content:
                trimmed = content[:8000]
                if len(content) > 8000:
                    trimmed += "\n... [truncated]"
                snippets.append(f"--- {path} ---\n{trimmed}")
        return "\n\n".join(snippets) if snippets else "(files not fetched)"

    def _relevant_diff(self, context: PRContext, issue: Issue) -> str:
        if not issue.related_files:
            return context.diff[:12000]
        lines = context.diff.splitlines(keepends=True)
        relevant: list[str] = []
        capturing = False
        for line in lines:
            if line.startswith("diff --git"):
                capturing = any(f in line for f in issue.related_files)
            if capturing:
                relevant.append(line)
        text = "".join(relevant)
        return text[:12000] if text else context.diff[:12000]
