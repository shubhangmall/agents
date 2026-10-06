"""Suggested follow-up questions shown after a research run (ux-06).

After the report completes, one small LLM call proposes 3-4 clickable
follow-up question chips ("Compare with X", "Go deeper on Y") that populate
the query box and invite a second run — the cheapest engagement loop
available. The UI renders them as gr.Button chips; clicking one fills the
query box (the user still presses Run).

Robustness: if the LLM call fails for any reason, query-derived template
suggestions are used instead. Failed or empty runs produce no chips at all.
This feature can never break the main research pipeline.
"""

import logging

from pydantic import BaseModel, Field, ValidationError

from llm_client import get_llm_client

MAX_SUGGESTIONS = 4
MAX_QUESTION_CHARS = 140
REPORT_CONTEXT_CHARS = 3000


class FollowupQuestions(BaseModel):
    questions: list[str] = Field(
        default_factory=list,
        description="3-4 short follow-up research questions a curious reader would ask next.",
    )


def build_followup_prompt(query: str, report_text: str) -> str:
    """Build the small prompt used for the follow-up suggestion LLM call."""
    context = (report_text or "").strip()
    if len(context) > REPORT_CONTEXT_CHARS:
        context = context[:REPORT_CONTEXT_CHARS] + "…"
    return (
        "Suggest 3-4 short follow-up research questions a curious reader would ask "
        "after reading the report below. Vary the angles: comparisons ('Compare X with Y'), "
        "deeper dives ('Go deeper on Z'), risks/limitations, and recent developments. "
        "Each question must stand alone as a new research query. "
        "Return only the requested JSON structure.\n\n"
        f"Original query: {query}\n\n"
        f"Report:\n{context}"
    )


def clean_questions(raw) -> list[str]:
    """Normalize raw suggestions: strip, drop empties/dupes, cap count and length."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in raw or []:
        if item is None:
            continue
        question = str(item).strip()
        if len(question) > MAX_QUESTION_CHARS:
            question = question[: MAX_QUESTION_CHARS - 1].rstrip() + "…"
        key = question.lower()
        if not question or key in seen:
            continue
        seen.add(key)
        cleaned.append(question)
        if len(cleaned) >= MAX_SUGGESTIONS:
            break
    return cleaned


def template_fallback(query: str) -> list[str]:
    """Query-derived templates used when the LLM suggestion call fails."""
    topic = (query or "").strip() or "this topic"
    return clean_questions(
        [
            f"Compare {topic} with the main alternatives",
            f"Go deeper on the key findings about {topic}",
            f"What are the risks and limitations of {topic}?",
            f"What are the latest developments in {topic}?",
        ]
    )


def _parse_questions_text(text: str | None) -> list[str]:
    """Best-effort parse of the raw LLM text into question strings."""
    if not isinstance(text, str) or not text.strip():
        return []
    normalized = text.strip()
    lines = normalized.splitlines()
    if (
        len(lines) >= 3
        and lines[0].strip().lower() in {"```", "```json"}
        and lines[-1].strip() == "```"
    ):
        normalized = "\n".join(lines[1:-1]).strip()
    try:
        return clean_questions(FollowupQuestions.model_validate_json(normalized).questions)
    except (ValidationError, ValueError):
        return []


async def suggest_followups(query: str, report_text: str) -> list[str]:
    """Propose follow-up questions via one small LLM call.

    Falls back to query-derived templates on any failure (or unusable
    output), so the chips always render for a successful run.
    """
    try:
        response = await get_llm_client().generate_structured(
            build_followup_prompt(query, report_text),
            schema=FollowupQuestions,
            temperature=0.4,
            max_tokens=300,
        )
        if isinstance(response.parsed, FollowupQuestions):
            questions = clean_questions(response.parsed.questions)
        else:
            questions = _parse_questions_text(response.text)
        if questions:
            return questions
        logging.warning("Follow-up suggestion call returned no usable questions")
    except Exception:
        logging.warning("Follow-up suggestion call failed; using templates", exc_info=True)
    return template_fallback(query)


def report_failed(report_text: str | None) -> bool:
    """True when the run did not produce a report (error placeholder shown).

    Both failure paths in deep_research.py render a message starting with ⚠️.
    """
    return not isinstance(report_text, str) or report_text.lstrip().startswith("⚠️")


async def followup_questions_for(query: str, report_text: str) -> list[str]:
    """Questions to show as chips after a run; [] when there is no report.

    Skips the LLM call entirely for failed or empty runs.
    """
    if not (query or "").strip() or not (report_text or "").strip():
        return []
    if report_failed(report_text):
        return []
    return await suggest_followups(query, report_text)
