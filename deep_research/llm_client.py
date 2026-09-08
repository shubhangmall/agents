from collections.abc import AsyncIterator
from dataclasses import dataclass
import json
from typing import Any

import httpx

from config import Settings, require_llm_settings
from provider_errors import (
    ProviderError,
    ProviderConfigurationError,
    ProviderRateLimitError,
    ProviderUnavailableError,
    StructuredOutputError,
    UnsupportedProviderCapabilityError,
    WriterStreamError,
)


@dataclass(frozen=True)
class _Endpoint:
    url: str
    headers: dict[str, str]


@dataclass(frozen=True)
class StructuredResponse:
    text: str
    parsed: Any = None


_CAPABILITIES = {
    ("openrouter", "openrouter/free"): {"structured": "json_object", "streaming": True},
    ("groq", "llama-3.3-70b-versatile"): {"structured": "json_object", "streaming": True},
    ("ollama", "llama3.2"): {"structured": "json_object", "streaming": True},
}


class LLMClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        require_llm_settings(settings)

    def _endpoint(self) -> _Endpoint:
        if self.settings.llm_provider == "openrouter":
            return _Endpoint(
                "https://openrouter.ai/api/v1/chat/completions",
                {"Authorization": f"Bearer {self.settings.openrouter_api_key}"},
            )
        if self.settings.llm_provider == "groq":
            return _Endpoint(
                "https://api.groq.com/openai/v1/chat/completions",
                {"Authorization": f"Bearer {self.settings.groq_api_key}"},
            )
        if self.settings.llm_provider == "ollama":
            return _Endpoint(f"{self.settings.ollama_base_url}/v1/chat/completions", {})
        raise ProviderConfigurationError("Unsupported LLM_PROVIDER")

    def _model(self) -> str:
        return self.settings.ollama_model if self.settings.llm_provider == "ollama" else self.settings.llm_model

    def _capabilities(self) -> dict[str, Any]:
        capabilities = _CAPABILITIES.get((self.settings.llm_provider, self._model()))
        if capabilities is None:
            raise UnsupportedProviderCapabilityError(
                "Configured provider/model has no declared capability contract"
            )
        return capabilities

    async def _request(self, payload: dict[str, Any]) -> httpx.Response:
        endpoint = self._endpoint()
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                return await client.post(
                    endpoint.url,
                    headers={**endpoint.headers, "Content-Type": "application/json"},
                    json=payload,
                )
        except httpx.HTTPError as error:
            raise ProviderUnavailableError("LLM provider is unavailable") from error

    @staticmethod
    def _check_response(response: httpx.Response) -> None:
        if response.status_code in {401, 403}:
            raise ProviderConfigurationError("LLM provider authentication failed")
        if response.status_code == 429:
            raise ProviderRateLimitError("LLM provider rate limit reached")
        if response.status_code >= 500:
            raise ProviderUnavailableError("LLM provider is unavailable")
        if response.status_code >= 400:
            raise ProviderUnavailableError("LLM provider request failed")

    def _structured_response_format(self, schema: Any) -> dict[str, Any]:
        mode = self._capabilities()["structured"]
        if mode == "json_object" or schema is None:
            return {"type": "json_object"}

        try:
            json_schema = schema.model_json_schema()
        except (AttributeError, TypeError, ValueError) as error:
            raise StructuredOutputError("Structured output schema is invalid") from error
        json_schema.setdefault("additionalProperties", False)
        name = getattr(schema, "__name__", "structured_output").lower()
        return {
            "type": "json_schema",
            "json_schema": {
                "name": name,
                "strict": True,
                "schema": json_schema,
            },
        }

    async def generate_text(self, prompt: str) -> str:
        response = await self._request(
            {"model": self._model(), "messages": [{"role": "user", "content": prompt}]}
        )
        self._check_response(response)
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise ProviderUnavailableError("LLM provider returned an unusable response") from error
        if not isinstance(content, str):
            raise ProviderUnavailableError("LLM provider returned an unusable response")
        return content

    async def generate_structured(
        self,
        prompt: str,
        schema: Any = None,
        *,
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> StructuredResponse:
        self._capabilities()
        response = await self._request(
            {
                "model": self._model(),
                "messages": [{"role": "user", "content": prompt}],
                "response_format": self._structured_response_format(schema),
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        self._check_response(response)
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise StructuredOutputError("LLM provider returned no structured output") from error
        if not isinstance(content, str) or not content.strip():
            raise StructuredOutputError("LLM provider returned no structured output")
        parsed = None
        if schema is not None:
            try:
                parsed = schema.model_validate_json(content)
            except (AttributeError, TypeError, ValueError):
                parsed = None
        return StructuredResponse(text=content, parsed=parsed)

    async def stream_text(
        self,
        prompt: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 1800,
    ) -> AsyncIterator[str]:
        capabilities = self._capabilities()
        if not capabilities["streaming"]:
            raise UnsupportedProviderCapabilityError(
                "Configured provider/model does not support the streaming protocol"
            )
        endpoint = self._endpoint()
        payload = {
            "model": self._model(),
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                async with client.stream(
                    "POST",
                    endpoint.url,
                    headers={**endpoint.headers, "Content-Type": "application/json"},
                    json=payload,
                ) as response:
                    self._check_response(response)
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            return
                        try:
                            content = json.loads(data)["choices"][0].get("delta", {}).get("content")
                        except (ValueError, KeyError, IndexError, TypeError) as error:
                            raise WriterStreamError("Writer stream returned invalid data") from error
                        if content:
                            yield content
        except ProviderError:
            raise
        except httpx.HTTPError as error:
            raise WriterStreamError("Writer stream was interrupted") from error


def get_llm_client(settings: Settings | None = None) -> LLMClient:
    return LLMClient(settings or Settings.from_env())
