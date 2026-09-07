from pydantic import BaseModel, Field, ValidationError

from llm_client import get_llm_client
from provider_errors import StructuredOutputError

HOW_MANY_SEARCHES = 5


class WebSearchItem(BaseModel):
    reason: str = Field(description="Why this search is important to the query.")
    query: str = Field(description="The web search query to run.")


class WebSearchPlan(BaseModel):
    searches: list[WebSearchItem] = Field(
        description="A bounded list of web searches needed to answer the query."
    )


class PlannerStructuredOutputError(StructuredOutputError):
    """The planner response was not valid structured output."""


def _parse_plan_text(text: str | None) -> WebSearchPlan:
    if not isinstance(text, str) or not text.strip():
        raise PlannerStructuredOutputError(
            "Planner returned no structured output."
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
        return WebSearchPlan.model_validate_json(normalized)
    except (ValidationError, ValueError) as error:
        raise PlannerStructuredOutputError(
            "Planner returned invalid structured output."
        ) from error


async def plan_searches(query: str) -> WebSearchPlan:
    prompt = (
        f"Create no more than {HOW_MANY_SEARCHES} distinct web searches for this research query. "
        "Return only the requested JSON structure. Avoid redundant searches.\n\n"
        f"Research query: {query}"
    )
    response = await get_llm_client().generate_structured(
        prompt,
        schema=WebSearchPlan,
        temperature=0.2,
        max_tokens=800,
    )
    if isinstance(response.parsed, WebSearchPlan):
        plan = response.parsed
    else:
        plan = _parse_plan_text(response.text)
    return WebSearchPlan(searches=plan.searches[:HOW_MANY_SEARCHES])
