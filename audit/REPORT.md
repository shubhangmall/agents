# Audit report

The highest-friction current issue is broken setup guidance in two subprojects, which conflicts with the repository's own “follow the README” rule.
The most important agent-quality issue is Sidekick's evaluator being told to trust completion claims instead of evidence.
The Agent-Creating-Agent creator prompt has contradictory generation constraints that make output behavior less predictable.
Two lower-risk prompt cleanups can remove unnecessary format anchoring/emphasis without changing intended behavior.
No local Claude/Codex session history was accessible, so this report contains no unverified session-derived conclusions.

Baseline: protected `master` at `e50a1ea7da305df2468a7d0b20708c458c37b82b`.

## Ranked confirmed findings

| Priority | Finding | Impact | Effort |
|---|---|---|---|
| 1 | Fix two broken README install paths | High | Low |
| 2 | Require evidence in Sidekick evaluator | High | Low |
| 3 | Make creator generation contract internally consistent | Medium-High | Low |
| 4 | Narrow Career Chatbot side-effect triggers | Medium | Low |
| 5 | Remove Sidekick clarification-format anchoring | Low-Medium | Low |
| 6 | Replace Engineering Team emphasis boosters with plain output contracts | Low | Low |

## 1. Fix broken README install paths

**Problem and evidence.** `agent_creating_agent/README.md:21` says `pip install -r requirements.txt`; `personal_sidekick/README.md:11` says the same. Neither directory contains that file. `AGENTS.md:32` tells coding agents to follow each project README and not invent commands, so the stale instructions create a deterministic setup dead-end.

**Proposed change.** Update only those setup sections to use the dependency source that is actually supported. Prefer documenting a root `uv`/lockfile workflow if these experiments intentionally share root dependencies; otherwise, as a separately approved implementation choice, add proper subproject manifests rather than pretending a requirements file exists.

**Affects.** `agent_creating_agent`, `personal_sidekick`, contributor/Codex setup reliability.

**Test.** From a clean environment, follow each revised README literally through dependency installation, then run the documented application/entry point far enough to prove imports resolve. Do not expose API keys.

## 2. Require evidence in the Sidekick evaluator

**Problem and evidence.** `personal_sidekick/sidekick.py:141` says to “give the Assistant the benefit of the doubt if they say they've done something.” This can mark a task complete even when a claimed file write or external action was not verified.

**Proposed change.** Replace that instruction with an evidence rule: external side effects count as complete only when supported by conversation/tool output; unsupported claims remain unverified and should trigger another worker step or user input when necessary.

**Affects.** `personal_sidekick` worker/evaluator loop and false-positive completion rate.

**Test.** Add/run a small evaluator sample with two transcripts: one where the worker merely claims a file was written and one where a tool result confirms it. The first must not pass solely on the claim; the second may pass when the success criteria are otherwise met. Run the app/sample flow to confirm the graph still terminates.

## 3. Make the creator prompt internally consistent

**Problem and evidence.** `agent_creating_agent/creator.py:30` calls the class constraint “the only requirement,” while line 43 says to generate “based strictly on this template,” and nearby text also says not to change method signatures. The allowed variation boundary is ambiguous.

**Proposed change.** Replace the conflicting prose with one contract: preserve `Agent`, `RoutedAgent` inheritance, constructor/handler signatures and runtime compatibility; vary the domain/system message (and only explicitly allowed implementation details); return raw Python only.

**Affects.** `agent_creating_agent` generation reliability and reproducibility.

**Test.** Generate several sample agents, parse/compile each, and assert the required class/inheritance/signatures are present. Start one generated agent through the existing runtime path and inspect that registration succeeds.

## 4. Narrow Career Chatbot side-effect triggers

**Problem and evidence.** `career_chatbot/app.py:186` tells the model to record *any* unanswered question; line 380 tells it to steer an engaged user toward email. These broad triggers can create noisy logging and unnecessary contact requests during ordinary conversation.

**Proposed change.** Preserve both tools but make their triggers intent-based: log unanswered questions relevant to the professional knowledge base; offer contact when the user asks to follow up or signals contact interest; record an address only when voluntarily supplied.

**Affects.** `career_chatbot` conversation quality, Pushover event volume, and contact-data collection behavior.

**Test.** Run scripted chats covering an unrelated trivia question, an unanswered career question, normal career discussion, and explicit contact interest. Confirm only the relevant knowledge gap is logged and only explicit contact intent leads to an email request/recording.

## 5. Remove Sidekick clarification-format anchoring

**Problem and evidence.** `personal_sidekick/sidekick.py:59-69` contains a useful stop condition plus a literal `Question: ...` example. The graph routes through structured evaluator output and does not parse that prefix, so the example is not required by the system.

**Proposed change.** Keep the stop condition but replace the example/ritual with: “If blocked by missing information, ask one concise clarification. Otherwise return the completed result.”

**Affects.** `personal_sidekick` prompt size and clarification style; no intended routing change.

**Test.** Run one task with sufficient information and one deliberately underspecified task. Confirm the first completes without a gratuitous question and the second asks a concise clarification; verify evaluator routing remains correct.

## 6. Replace Engineering Team emphasis boosters with plain output contracts

**Problem and evidence.** `engineering_team/src/engineering_team/config/tasks.yaml:6,18,33,45` uses repeated `IMPORTANT`/all-caps output directives. The constraints themselves are valid and should remain, but capitalization is unnecessary.

**Proposed change.** Preserve each task-local requirement in plain, testable language. Example for code tasks: “Return raw Python only: no Markdown fences or commentary. The saved output must parse as Python.”

**Affects.** `engineering_team` prompt clarity only; output format must remain unchanged.

**Test.** Run the crew's normal sample task. Confirm generated backend/frontend/test files contain no fences or commentary, run `python -m py_compile` on generated Python, and run the generated `python -m unittest test_accounts.py` check where applicable.

## Not recommended for change

The repository-level secrets, branch safety, unrelated-change, and validation rules in `AGENTS.md` are useful and proportionate. The current `deep_research` prompts/provider contracts were checked and do not show the stale workarounds this audit is targeting. The 20 generated numbered agent files are retained as experiment artifacts rather than deleted merely because their prompts are verbose.

## Phase 3 limitation

No accessible local files existed under `~/.claude/projects/` or `~/.codex/sessions/`, and no session logs are checked into the repository. Accordingly, no historical observation was treated as a confirmed current problem without repository evidence.

## Stop point

Phases 1-5 are complete on the audit branch. No file outside `audit/` has been modified. Await explicit approval of specific numbered items before Phase 6.
