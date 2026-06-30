# PR Merge-Readiness Agent

A multi-agent assistant that triages GitHub pull requests, analyzes CI failures and unresolved review comments, and proposes scoped fixes **without pushing commits**. Built by **Shubhang Mall** using the OpenAI Agents SDK and Gradio.

## How It Works

- **Triage Agent** categorizes blocking issues: CI failures, review comments, merge conflicts.
- **Fix Agent** proposes patches and draft replies scoped to PR-changed files only.
- **Reporter Agent** assembles a merge-readiness report with a verdict (`ready`, `blocked`, or `needs_review`).
- **PRManager** orchestrates the pipeline and streams status updates to the UI.

The agent runs in **advisory mode**: it never commits, pushes, or modifies CI workflows.

## Prerequisites

1. **Python 3.10+**
2. **GitHub CLI** authenticated:

   ```bash
   gh auth login
   gh auth status   # should succeed
   ```

3. **OpenAI API key** in environment or `.env`

## Installation

```bash
cd pr_agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and set OPENAI_API_KEY
```

## Running

```bash
python pr_agent.py
```

A Gradio interface opens at `http://localhost:7860`. Paste a PR URL, click **Analyze**, and review the report. Optionally click **Post comment to PR** to publish the report as a PR comment.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | (required) | OpenAI API key |
| `PR_AGENT_MODEL` | `gpt-4o-mini` | Model for triage and reporter |
| `PR_FIX_MODEL` | `gpt-4o` | Model for fix proposals |
| `GITHUB_TOKEN` | (optional) | Fallback if `gh auth` is not configured |

## Safety & Scope (v1)

**Will not:**
- Push commits or open new PRs
- Modify `.github/workflows/` or CI configuration
- Auto-merge or resolve merge conflicts automatically

**Will:**
- Propose lint/import/type/test fixes for changed files
- Draft replies to unresolved review comments
- Recommend merging latest base branch when relevant

## Manual Test Plan

1. **Green PR** — Run against a PR with passing CI and no open comments. Expect verdict `ready`.
2. **Lint failure** — Run against a PR with a lint error in changed files. Expect a `ProposedFix` with a patch.
3. **Review comment** — Run against a PR with an unresolved review thread. Expect a drafted reply in the report.
4. **Post comment** — After analysis, click **Post comment to PR**. Verify the comment appears on GitHub and the button disables to prevent duplicates.

## Project Structure

```
pr_agent/
  pr_agent.py           # Gradio UI
  pr_manager.py         # Orchestrator
  github_client.py      # gh CLI wrapper
  models.py             # Pydantic schemas
  triage_agent.py
  fix_agent.py
  reporter_agent.py
```

## Why This Matters

This project demonstrates a practical agent workflow for developer tooling: read real PR state via GitHub CLI, triage with specialized agents, propose verifiable fixes, and optionally publish results—all without destructive git operations.
