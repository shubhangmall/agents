from dataclasses import dataclass

import httpx

from config import Settings, require_search_settings
from provider_errors import SearchProviderError


@dataclass(frozen=True)
class SearchHit:
    title: str
    url: str
    content: str


class SearchClient:
    async def search(self, query: str) -> list[SearchHit]:
        raise NotImplementedError


class TavilySearchClient(SearchClient):
    def __init__(self, settings: Settings):
        require_search_settings(settings)
        self.settings = settings

    async def search(self, query: str) -> list[SearchHit]:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": self.settings.tavily_api_key,
                        "query": query,
                        "search_depth": "basic",
                        "max_results": self.settings.search_max_results,
                        "include_answer": False,
                        "include_raw_content": False,
                    },
                )
        except httpx.HTTPError as error:
            raise SearchProviderError("Search provider is unavailable") from error
        if response.status_code in {401, 403}:
            raise SearchProviderError("Search provider authentication failed")
        if response.status_code == 429:
            raise SearchProviderError("Search provider rate limit reached")
        if response.status_code >= 400:
            raise SearchProviderError("Search provider request failed")
        try:
            results = response.json().get("results", [])
            return [
                SearchHit(
                    title=str(item.get("title", "")),
                    url=str(item.get("url", "")),
                    content=str(item.get("content", "")),
                )
                for item in results
                if isinstance(item, dict)
            ]
        except (AttributeError, TypeError, ValueError) as error:
            raise SearchProviderError("Search provider returned invalid data") from error


def get_search_client(settings: Settings | None = None) -> SearchClient:
    resolved = settings or Settings.from_env()
    if resolved.search_provider == "tavily":
        return TavilySearchClient(resolved)
    raise SearchProviderError("Unsupported search provider")
