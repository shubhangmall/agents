# Prompt and instruction audit

Only issues that remain present in the current `master` tree are listed here. Security/secrets rules in `AGENTS.md` are retained unchanged.

## 1. Stale install commands conflict with repository guidance

### agent_creating_agent/README.md:21
Exact text: `pip install -r requirements.txt  # install openai, autogen, etc.`

### personal_sidekick/README.md:11
Exact text: `pip install -r requirements.txt`

### AGENTS.md:32
Exact text: `Follow each project README for application run commands; do not invent additional test commands.`

Why it hurts: neither subproject contains a `requirements.txt`. An agent following the repository instruction reaches a guaranteed missing-file failure and is simultaneously discouraged from deriving an alternative command. This is current documentation friction, not historical drift.

Proposed rewrite: make each README use the dependency source that actually exists. For `agent_creating_agent` and `personal_sidekick`, either document installation from the root `pyproject.toml`/lockfile or add a real subproject dependency manifest in a later approved implementation. Keep `AGENTS.md`'s anti-invention rule.

## 2. Creator prompt contains conflicting structural constraints

### agent_creating_agent/creator.py:30
Exact text: `You can choose to take this Agent in a completely different direction. The only requirement is that the class must be named Agent,`

### agent_creating_agent/creator.py:43
Exact text: `Please generate a new Agent based strictly on this template. Stick to the class structure.`

Why it hurts: “completely different direction,” “only requirement,” and “based strictly on this template” describe different constraint boundaries. The prompt also separately says not to change method signatures, so “only requirement” is factually false. This increases variance in generated code and makes failures harder to attribute.

Proposed rewrite: state one explicit contract: preserve class name, inheritance, constructor and required handler signatures; preserve runtime compatibility; vary only the system message/domain unless a named extension point permits code changes; return raw Python only.

## 3. Sidekick evaluator is instructed to trust unverifiable completion claims

### personal_sidekick/sidekick.py:141
Exact text: `Overall you should give the Assistant the benefit of the doubt if they say they've done something. But you should reject if you feel that more work should go into this.`

Why it hurts: this weakens the evaluator exactly where agent workflows need evidence. A worker can claim a file/action succeeded and receive a pass without the evaluator inspecting a tool result or artifact. It creates false-positive completion and masks tool failures.

Proposed rewrite: evaluate completion from conversation/tool evidence. Treat an unsupported claim as unverified; require the worker to inspect or report the relevant tool result when the success criterion depends on an external side effect.

## 4. Sidekick worker uses an unnecessary output ritual and anchored example

### personal_sidekick/sidekick.py:59
Exact text: `You keep working on a task until either you have a question or clarification for the user, or the success criteria is met.`

### personal_sidekick/sidekick.py:69
Exact text: `Question: please clarify whether you want a summary or a detailed answer`

Why it hurts: the stop condition is useful, but the literal “Question:” example is an unnecessary format anchor. It can bias ordinary clarifications toward a canned form and adds prompt tokens without improving routing, because routing is performed by the evaluator's structured output rather than by parsing this prefix.

Proposed rewrite: keep the semantic stop rule, remove the example and prefix ritual: “If blocked by missing information, ask one concise clarification. Otherwise return the completed result.”

## 5. Career chatbot prompt over-triggers logging and lead capture

### career_chatbot/app.py:186
Exact text: `Always use this tool to record any question that couldn't be answered as you didn't know the answer`

### career_chatbot/app.py:380
Exact text: `If the user is engaging in discussion, try to steer them towards getting in touch via email; ask for their email and record it using your record_user_details tool.`

Why it hurts: “any question,” including trivial or unrelated questions, creates noisy side effects. “If the user is engaging” is so broad that ordinary conversation can trigger an email request, adding friction and collecting contact data before the user signals contact intent.

Proposed rewrite: preserve the lead-capture capability but narrow triggers. Record unanswered questions only when relevant to the site's professional-purpose knowledge gap. Offer contact details when the user asks to follow up or expresses interest in contacting the person; record an email only when the user voluntarily provides it.

## 6. Engineering Team repeats emphasis boosters in task outputs

### engineering_team/src/engineering_team/config/tasks.yaml:6
Exact text begins: `IMPORTANT: Only output the design in markdown format...`

### engineering_team/src/engineering_team/config/tasks.yaml:18, 33, 45
Exact text begins: `IMPORTANT: Output ONLY the raw Python code...`

Why it hurts: capitalization is being used as an emphasis booster where a plain output contract is sufficient. The three code-producing tasks legitimately need the constraint independently, so the requirement should remain in each task; only the booster and excess wording are unnecessary.

Proposed rewrite: use direct testable wording such as `Return raw Python only: no Markdown fences or commentary. The saved output must parse as Python.` For the design task: `Return Markdown containing only the design.`

## Reviewed but not recommended for removal

- `AGENTS.md` secrets, branch-isolation, unrelated-change, and validation rules are concise and useful.
- `deep_research` planner/writer prompts are bounded and align with current provider/evidence controls; no prompt simplification is recommended.
- The 20 numbered `agent_creating_agent/agent*.py` system messages are generated experiment artifacts. They are verbose in aggregate but are part of that experiment's observable output, so they should not be deleted merely to reduce prompt inventory size.
- Stock/financial Crew prompts contain strong task goals, but this audit found no instruction-level contradiction that should be changed solely for brevity.
