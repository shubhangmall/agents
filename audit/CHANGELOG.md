# Audit changelog

Date: 2026-09-27
Branch: `audit/instruction-friction-2026-09-27`
Baseline: `master` at `e50a1ea7da305df2468a7d0b20708c458c37b82b`

## Applied

1. **Setup guidance** — `agent_creating_agent/README.md` and `personal_sidekick/README.md` now use the checked-in repository-level `pyproject.toml`/`uv.lock` workflow instead of nonexistent local `requirements.txt` files.
2. **Sidekick evaluator evidence** — replaced instructions that trusted completion claims with an explicit requirement for conversation/tool evidence for external side effects.
3. **Agent creator contract** — replaced conflicting “only requirement”/“strict template” language with one runtime-compatibility contract covering class name, inheritance, constructor, handler signatures, and raw-Python output.
4. **Career Chatbot side effects** — narrowed unknown-question logging to relevant professional knowledge gaps and contact capture to explicit follow-up/contact intent plus a voluntarily provided email.
5. **Sidekick clarification style** — removed the canned `Question:` example and kept a concise semantic clarification rule.
6. **Engineering Team output contracts** — removed `IMPORTANT`/all-caps emphasis while preserving task-local Markdown/raw-Python output requirements.
7. **Durable guidance** — added the resulting prompt/evaluator/side-effect/setup decisions to root `AGENTS.md`.

## Validation performed

- Re-read each changed file on the audit branch after its update.
- Compared the branch against the original `master` baseline to confirm changes are limited to the six approved implementation areas, `AGENTS.md`, and `audit/`.
- Confirmed the setup instructions now reference dependency files that exist in the repository.
- Confirmed the prompt edits preserve existing class/function signatures and output contracts.

## Validation not executable in this runtime

The connected GitHub environment exposes repository contents and mutations but not a checked-out shell workspace. Therefore `git diff --check`, `python -m py_compile`, clean `uv sync`, live LLM sample generations, Gradio browser inspection, and CrewAI sample execution could not be run here. These checks are not reported as passing.

## Skipped

- No audit finding was skipped after approval.
- No secrets or environment values were read or changed.
- No generated `agent1.py`–`agent20.py` artifacts were rewritten.
- No `deep_research` behavior was changed because its previously repaired provider/evidence contracts were verified as current during the audit.
- No PR was opened and nothing was merged; branch integration remains a separate explicit action.
