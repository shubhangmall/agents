from dataclasses import dataclass
from hashlib import sha256
from urllib.parse import urlparse

from google.genai import types

from gemini_client import generate_content
from planner_agent import WebSearchItem


@dataclass(frozen=True)
class ResearchSource:
    id: str
    title: str
    url: str
    domain: str


@dataclass(frozen=True)
class SearchResult:
    query: str
    summary: str
    sources: tuple[ResearchSource, ...]


def _source_id(url: str) -> str:
    return f"source-{sha256(url.encode('utf-8')).hexdigest()[:10]}"


def _sources_from_response(response) -> tuple[ResearchSource, ...]:
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return ()
    metadata = getattr(candidates[0], "grounding_metadata", None)
    chunks = getattr(metadata, "grounding_chunks", None) or []
    sources: list[ResearchSource] = []
    seen_urls: set[str] = set()
    for chunk in chunks:
        web = getattr(chunk, "web", None)
        url = getattr(web, "uri", None) if web else None
        title = getattr(web, "title", None) if web else None
        if not url or url in seen_urls:
            continue
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        seen_urls.add(url)
        sources.append(
            ResearchSource(
                id=_source_id(url),
                title=title or parsed.netloc,
                url=url,
                domain=parsed.netloc,
            )
        )
    return tuple(sources)


async def search_web(item: WebSearchItem) -> SearchResult:
    prompt = (
        "Research the following search query using current web sources. "
        "Write a concise evidence summary for a report writer. Do not invent URLs or sources; "
        "source provenance will be read from grounding metadata.\n\n"
        f"Search query: {item.query}\n"
        f"Reason: {item.reason}"
    )
    response = await generate_content(
        prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.2,
            max_output_tokens=700,
        ),
    )
    return SearchResult(
        query=item.query,
        summary=response.text or "No grounded summary was returned.",
        sources=_sources_from_response(response),
    )
