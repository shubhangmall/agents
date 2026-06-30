import os

from agents import Agent

from models import BabysitReport

INSTRUCTIONS = """You are a PR merge-readiness reporter. Given triaged issues and proposed fixes,
produce a clear markdown report for the PR author.

Verdict rules:
- ready: all CI green, no blocking issues, no merge conflicts
- blocked: merge conflicts, failing CI, or blocking review comments without acceptable fixes
- needs_review: fixes proposed but human should verify before merging

The markdown report must include:
1. A verdict header (## Verdict: READY / BLOCKED / NEEDS REVIEW)
2. Executive summary as bullet points (3-5 items)
3. Issues found section grouped by severity
4. Proposed fixes section with patches in fenced code blocks
5. Recommended next steps

Write in clear, actionable language. This report may be posted as a PR comment."""

reporter_agent = Agent(
    name="ReporterAgent",
    instructions=INSTRUCTIONS,
    model=os.getenv("PR_AGENT_MODEL", "gpt-4o-mini"),
    output_type=BabysitReport,
)
