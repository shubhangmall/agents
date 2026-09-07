import json

from google.genai import types
from pydantic import BaseModel, Field

from gemini_client import generate_content

HOW_MANY_SEARCHES = 5


class WebSearchItem(BaseModel):
    reason: str = Field(description="Why this search is important to the query.")
    query: str = Field(description="The web search query to run.")


class WebSearchPlan(BaseModel):
    searches: list[WebSearchItem] = Field(
        description="A bounded list of web searches needed to answer the query."
    )


async def plan_searches(query: str) -> WebSearchPlan:
    prompt = (
        f"Create no more than {HOW_MANY_SEARCHES} distinct web searches for this research query. "
        "Return only the requested JSON structure. Avoid redundant searches.\n\n"
        f"Research query: {query}"
    )
    response = await generate_content(
        prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=WebSearchPlan,
            temperature=0.2,
            max_output_tokens=800,
        ),
    )
    if isinstance(response.parsed, WebSearchPlan):
        plan = response.parsed
    else:
        plan = WebSearchPlan.model_validate(json.loads(response.text))
    return WebSearchPlan(searches=plan.searches[:HOW_MANY_SEARCHES])
