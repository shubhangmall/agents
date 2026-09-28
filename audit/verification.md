# Phase 4 verification

Baseline rechecked before reporting: protected `master` still points to `e50a1ea7da305df2468a7d0b20708c458c37b82b`.

## Verified current problems

1. **Broken README install commands** — verified by current tree: `agent_creating_agent/README.md:21` and `personal_sidekick/README.md:11` reference local `requirements.txt` files that do not exist. Root `AGENTS.md:32` tells agents to follow project READMEs and not invent commands.
2. **Creator prompt contradiction** — verified in current `agent_creating_agent/creator.py`: line 30 says the class name/inheritance/constructor are “the only requirement,” while line 43 says to follow the template strictly, and adjacent prompt text also forbids method-signature changes.
3. **Sidekick evaluator trusts claims** — verified at `personal_sidekick/sidekick.py:141`.
4. **Sidekick clarification format anchoring** — verified at `personal_sidekick/sidekick.py:59-69`; routing does not parse a literal `Question:` prefix, so the example is not structurally required.
5. **Career chatbot broad side-effect triggers** — verified at `career_chatbot/app.py:186` and line 380.
6. **Engineering prompt emphasis boosters** — verified at `engineering_team/src/engineering_team/config/tasks.yaml:6,18,33,45`.

## Historical observations dropped

No local session-history findings were available, so none were promoted into current problems.

The recently repaired `deep_research` provider capability/evidence-bound behavior was inspected in the current tree and is not included as an audit problem. Its README and prompt contracts align with the present implementation.

## Read-only checks and limitations

- Repository tree inspected recursively through the connected GitHub repository.
- Exact current file contents and relevant line locations re-read from `master`.
- Default branch/head rechecked immediately before reporting.
- No `.github/` workflows exist, so there is no CI result to use as a verification signal.
- The execution container does not have the repository mounted and cannot reach GitHub directly, so local test/build/lint execution was not possible without first creating a separate checkout. No project execution was attempted because the audit is instruction-focused and the confirmed findings above are statically verifiable.
- Phase 6 test plans therefore include executable validation after approval.
