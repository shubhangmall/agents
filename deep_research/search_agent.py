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


def _evidence_summary(hits: list[SearchHit], sources: tuple[ResearchSource, ...], max_chars: int = 12000) -> str:
    source_by_url = {source.url: source for source in sources}
    sections = []
    remaining = max_chars
    seen_urls: set[str] = set()
    for hit in hits:
        url = hit.url.strip()
        source = source_by_url.get(url)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        if source and hit.content.strip() and remaining > 0:
            prefix = f"[{source.id}] {source.title}\n"
            content = hit.content.strip()
            available = remaining - len(prefix) - (2 if sections else 0)
            if available <= 0:
                break
            content = content[:available]
            sections.append(prefix + content)
            remaining -= len(prefix) + len(content) + (2 if len(sections) > 1 else 0)
    return "\n\n".join(sections) or "No search evidence was returned."


def _budget_hits(hits: list[SearchHit], max_chars: int) -> list[SearchHit]:
    accepted: list[SearchHit] = []
    remaining = max_chars
    seen_urls: set[str] = set()
    for hit in hits:
        url = hit.url.strip()
        if url in seen_urls or not hit.content.strip():
            continue
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        seen_urls.add(url)
        title = hit.title.strip() or parsed.netloc
        prefix_length = len(f"[source-{'x' * 10}] {title}\n")
        available = remaining - prefix_length - (2 if accepted else 0)
        if available <= 0:
            break
        content = hit.content.strip()[:available]
        accepted.append(SearchHit(hit.title, hit.url, content))
        remaining -= prefix_length + len(content) + (2 if len(accepted) > 1 else 0)
    return accepted


async def search_web(item: WebSearchItem, settings: Settings | None = None) -> SearchResult:
    settings = settings or Settings.from_env()
    hits = _budget_hits(await get_search_client(settings).search(item.query), settings.search_evidence_max_chars)
    sources = _normalize_hits(hits)
    return SearchResult(
        query=item.query,
        summary=_evidence_summary(hits, sources, settings.search_evidence_max_chars),
        sources=sources,
    )
