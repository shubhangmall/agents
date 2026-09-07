import json
from collections.abc import AsyncIterator

from gemini_client import stream_content
from search_agent import SearchResult


def _evidence_context(results: list[SearchResult]) -> str:
    evidence = []
    for result in results:
        evidence.append(
            {
                "query": result.query,
                "summary": result.summary,
                "sources": [source.__dict__ for source in result.sources],
            }
        )
    return json.dumps(evidence, ensure_ascii=False, indent=2)


async def stream_report(query: str, search_results: list[SearchResult]) -> AsyncIterator[str]:
    prompt = (
        "Write a grounded Markdown research report for the user's query using only the evidence "
        "below. Do not add facts that are not supported by the evidence. Cite claims with the "
        "provided source IDs in the form [source-XXXXXXXXXX]. Never invent a source ID or URL. "
        "If the evidence is insufficient, say so plainly. Keep the report concise for a public demo.\n\n"
        f"User query: {query}\n\n"
        f"Evidence:\n{_evidence_context(search_results)}"
    )
    async for chunk in stream_content(
        prompt,
        config={"temperature": 0.2, "max_output_tokens": 1800},
    ):
        yield chunk
