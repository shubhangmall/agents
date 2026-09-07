from dataclasses import dataclass
from hashlib import sha256
from urllib.parse import urlparse

from config import Settings
from search_client import SearchHit, get_search_client
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


def _normalize_hits(hits: list[SearchHit]) -> tuple[ResearchSource, ...]:
    sources: list[ResearchSource] = []
    seen_urls: set[str] = set()
    for hit in hits:
        url = hit.url.strip()
        title = hit.title.strip()
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


def _evidence_summary(hits: list[SearchHit], sources: tuple[ResearchSource, ...]) -> str:
    source_by_url = {source.url: source for source in sources}
    sections = []
    seen_urls: set[str] = set()
    for hit in hits:
        url = hit.url.strip()
        source = source_by_url.get(url)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        if source and hit.content.strip():
            sections.append(f"[{source.id}] {source.title}\n{hit.content.strip()}")
    return "\n\n".join(sections) or "No search evidence was returned."


async def search_web(item: WebSearchItem, settings: Settings | None = None) -> SearchResult:
    hits = await get_search_client(settings).search(item.query)
    sources = _normalize_hits(hits)
    return SearchResult(
        query=item.query,
        summary=_evidence_summary(hits, sources),
        sources=sources,
    )
