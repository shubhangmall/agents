# AGENTS.md

## Repository

This repository is a collection of independent Python AI-agent experiments and applications, using frameworks such as AutoGen, CrewAI, Gradio, and RAG tooling. Most projects are self-contained; prefer working within one project at a time.

- Default branch: `master`.
- `deep_research/`: web research planner, search, writer, and optional email workflow.
- `career_chatbot/`: résumé/context RAG chatbot with a Gradio UI.
- `engineering_team/`: CrewAI engineering-code generation crew.
- `personal_sidekick/`: Gradio personal assistant with memory and tools.
- `stock_picker/`: CrewAI stock-analysis/recommendation crew.
- `agent_creating_agent/`: experimental AutoGen agents that generate other agents.

## Workflow

- Inspect the relevant README, dependency files, and current Git status before editing.
- Scope changes to one project when possible; preserve unrelated local changes.
- Use a clean branch or temporary worktree to isolate PR work when branch history or concurrent changes make that useful.
- Do not merge unless explicitly asked, force-push, or reset/discard unrelated work.

## Secrets and environment

- Never print, log, copy, or commit API keys or other credentials.
- Use each project’s ignored `.env`/`.env.example` pattern; load credentials temporarily in the environment when running commands.

## Checks

- Run `git diff --check` for every change.
- No repository-wide test runner is configured. The checked-in generated examples use `python -m unittest test_accounts.py` when run from their containing directory.
- For Python-only edits, use `python -m py_compile <changed-file>` when a syntax check is useful.
- Follow each project README for application run commands; do not invent additional test commands.

## Tool efficiency

- Prefer filesystem inspection and terminal tools.
- Do not use browser, web, or MCP tools unless the task requires them.
- Inspect only relevant directories/files, and avoid repo-wide scans once the relevant scope is known.
- Do not inspect or modify sibling projects unless the task requires it.
