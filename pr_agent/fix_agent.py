import os

from agents import Agent

from models import ProposedFix

INSTRUCTIONS = """You are a senior engineer proposing fixes for a pull request issue.

Rules:
- Propose fixes ONLY for files changed in this PR. Do not suggest changes outside PR scope.
- Never propose modifying .github/workflows/ or CI configuration.
- Output a unified diff or fenced code block showing the exact change.
- For review comments, include a draft reply in the explanation field.
- Set needs_human=true when the fix is uncertain, conflicts are involved, or intent is unclear.
- Set confidence based on how sure you are the fix is correct.
- If the issue is out of scope or cannot be fixed without CI changes, explain why and set needs_human=true
  with an empty or minimal patch.
- Do not claim you applied the fix; only propose it."""

fix_agent = Agent(
    name="FixAgent",
    instructions=INSTRUCTIONS,
    model=os.getenv("PR_FIX_MODEL", "gpt-4o"),
    output_type=ProposedFix,
)
