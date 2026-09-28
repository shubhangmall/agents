# Project instruction inventory

Audit target: `shubhangmall/agents`, default branch `master`, head observed at audit start: `e50a1ea7da305df2468a7d0b20708c458c37b82b`.

## Repository-level instructions and documentation
- `AGENTS.md` — repository coding-agent guidance.
- `README.md` — repository overview and setup guidance.
- No `CLAUDE.md`, `.claude/`, `.cursorrules`, equivalent Cursor rule file, or `.github/` workflow/instruction files found.
- No dedicated files with `prompt`, `spec`, `plan`, or `todo` in their filenames found.

## Subproject READMEs
- `agent_creating_agent/README.md`
- `career_chatbot/README.md`
- `deep_research/README.md`
- `engineering_team/README.md`
- `financial_researcher/README.md`
- `personal_sidekick/README.md`
- `stock_picker/README.md`

## Embedded prompts and prompt templates

### agent_creating_agent
- `agent_creating_agent/agent.py`
- `agent_creating_agent/creator.py`
- `agent_creating_agent/agent1.py` through `agent_creating_agent/agent20.py`
- Supporting orchestration/context reviewed: `messages.py`, `world.py`.
- The numbered agents are generated executable examples with distinct embedded system messages, not dedicated few-shot prompt files.

### career_chatbot
- `career_chatbot/app.py` — system prompt and tool descriptions.

### deep_research
- `deep_research/planner_agent.py` — planning prompt.
- `deep_research/writer_agent.py` — grounded report-writing prompt.
- Surrounding implementation/validation reviewed: `config.py`, `deep_research.py`, `email_agent.py`, `llm_client.py`, `provider_errors.py`, `research_manager.py`, `search_agent.py`, `search_client.py`, `test_deep_research.py`.

### engineering_team
- `engineering_team/src/engineering_team/config/agents.yaml`
- `engineering_team/src/engineering_team/config/tasks.yaml`
- Generated `example_output_4o/`, `example_output_new/`, and `output/` are code/output fixtures, not instruction files or prompt few-shots.

### financial_researcher
- `financial_researcher/src/financial_researcher/config/agents.yaml`
- `financial_researcher/src/financial_researcher/config/tasks.yaml`

### personal_sidekick
- `personal_sidekick/sidekick.py` — worker prompt, evaluator prompt, inline example response.
- `personal_sidekick/sidekick_tools.py` — tool implementation context.

### stock_picker
- `stock_picker/src/stock_picker/config/agents.yaml`
- `stock_picker/src/stock_picker/config/tasks.yaml`

## Plans, specs, TODOs, and few-shot examples
No dedicated plan/spec/TODO files were found by repository-tree inspection. The clear inline few-shot-style example found is the Sidekick worker's example clarification response in `personal_sidekick/sidekick.py`.

## Session history
The available runtime exposes no files under `~/.claude/projects/` or `~/.codex/sessions/`. No checked-in project session-history files were found. Phase 3 therefore records this limitation rather than inferring session findings from unrelated chat summaries.

## Verification surface
- No GitHub Actions workflow is checked in.
- Current test files found: `deep_research/test_deep_research.py` and generated Engineering Team `test_accounts.py` examples/outputs.
- Subproject requirements files exist for `career_chatbot/` and `deep_research/`; they do not exist for `agent_creating_agent/` or `personal_sidekick/`, despite both READMEs instructing `pip install -r requirements.txt`.
