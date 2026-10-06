"""Optional clarifying questions before a research run (ux-09).

Before planning, one extra LLM call produces up to MAX_QUESTIONS short
disambiguating questions (audience, depth, time period) with quick-reply
options. The Gradio UI renders them as a pre-run screen with a Skip option;
any answers are formatted into a clarifications block that the planner
prompt incorporates.

Never blocks: generate_questions() returns an empty list when the LLM judges
the query already specific, and callers must keep going (Skip/Continue) when
the LLM call fails — the UI shows the panel either way.

Only the standard library plus pydantic are used, mirroring planner_agent.
"""

from pydantic import BaseModel, Field

from llm_client import get_llm_client
from provider_errors import StructuredOutputError

MAX_QUESTIONS = 3
MAX_OPTIONS = 4


class ClarifyingQuestion(BaseModel):
    question: str = Field(
        description="One short disambiguating question about the research request."
    )
    options: list[str] = Field(
        description="2-4 concise quick-reply answer options for the question."
    )


class ClarifyingQuestions(BaseModel):
    questions: list[ClarifyingQuestion] = Field(
        description="Up to 3 clarifying questions; empty when the query is already specific."
    )


class ClarifyStructuredOutputError(StructuredOutputError):
    """The clarifying-questions response was not valid structured output."""


def _parse_questions_text(text: str | None) -> ClarifyingQuestions:
    if not isinstance(text, str) or not text.strip():
        raise ClarifyStructuredOutputError(
            "Clarifying questions returned no structured output."
        )

    normalized = text.strip()
    lines = normalized.splitlines()
    if (
        len(lines) >= 3
        and lines[0].strip().lower() in {"```", "```json"}
        and lines[-1].strip() == "```"
    ):
        normalized = "\n".join(lines[1:-1]).strip()

    try:
        return ClarifyingQuestions.model_validate_json(normalized)
    except ValueError as error:
        raise ClarifyStructuredOutputError(
            "Clarifying questions returned invalid structured output."
        ) from error


def sanitize_questions(questions) -> list[ClarifyingQuestion]:
    """Cap counts, drop empties; never raises on model-shaped input."""
    clean: list[ClarifyingQuestion] = []
    for item in questions or []:
        text = (getattr(item, "question", "") or "").strip()
        options = [
            option.strip()
            for option in (getattr(item, "options", None) or [])
            if isinstance(option, str) and option.strip()
        ][:MAX_OPTIONS]
        if not text or len(options) < 2:
            continue
        clean.append(ClarifyingQuestion(question=text, options=options))
        if len(clean) >= MAX_QUESTIONS:
            break
    return clean


async def generate_questions(query: str) -> list[ClarifyingQuestion]:
    """Ask the LLM for up to MAX_QUESTIONS clarifying questions about query.

    Returns [] when the query is already specific. Raises on provider
    failures (ProviderError subclasses) — callers must treat that as
    "no questions" and keep the run skippable.
    """
    prompt = (
        "You are refining a research request before a deep research agent runs. "
        "The user asked:\n\n"
        f"{query}\n\n"
        "Ask up to 3 short, specific clarifying questions that would meaningfully "
        "improve the research results (for example: intended audience, desired depth, "
        "time period, or geographic scope). Each question must offer 2-4 concise "
        "quick-reply options. Ask only questions whose answers would change what to "
        "research — never ask for facts, and never answer the request yourself. "
        "If the request is already fully specific, return an empty questions list. "
        "Return only the requested JSON structure."
    )
    response = await get_llm_client().generate_structured(
        prompt,
        schema=ClarifyingQuestions,
        temperature=0.7,
        max_tokens=600,
    )
    if isinstance(response.parsed, ClarifyingQuestions):
        parsed = response.parsed
    else:
        parsed = _parse_questions_text(response.text)
    return sanitize_questions(parsed.questions)


def format_clarifications(answers: list[tuple[str, str]]) -> str | None:
    """Render answered (question, answer) pairs into a planner-prompt block.

    Returns None when there is nothing usable, so callers can treat "no
    answers" exactly like a skipped screen.
    """
    pairs = [
        (str(question).strip(), str(answer).strip())
        for question, answer in (answers or [])
        if str(question or "").strip() and str(answer or "").strip()
    ]
    if not pairs:
        return None
    lines = ["The user answered these optional clarifying questions about their request:"]
    lines.extend(f"- {question} → {answer}" for question, answer in pairs)
    return "\n".join(lines)
