from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv
from provider_errors import ProviderConfigurationError


load_dotenv(Path(__file__).with_name(".env"), override=False)


class ConfigurationError(ProviderConfigurationError):
    """A required provider configuration value is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    llm_provider: str
    llm_model: str
    openrouter_api_key: str | None
    groq_api_key: str | None
    ollama_base_url: str
    ollama_model: str
    search_provider: str
    tavily_api_key: str | None
    search_max_results: int
    search_evidence_max_chars: int = 12000

    @classmethod
    def from_env(cls) -> "Settings":
        try:
            max_results = int(os.getenv("SEARCH_MAX_RESULTS", "5"))
        except ValueError as error:
            raise ConfigurationError("SEARCH_MAX_RESULTS must be an integer") from error
        if max_results < 1 or max_results > 5:
            raise ConfigurationError("SEARCH_MAX_RESULTS must be between 1 and 5")
        try:
            evidence_max_chars = int(os.getenv("SEARCH_EVIDENCE_MAX_CHARS", "12000"))
        except ValueError as error:
            raise ConfigurationError("SEARCH_EVIDENCE_MAX_CHARS must be an integer") from error
        if evidence_max_chars < 1:
            raise ConfigurationError("SEARCH_EVIDENCE_MAX_CHARS must be positive")
        provider = os.getenv("LLM_PROVIDER", "openrouter").strip().lower()
        defaults = {
            "openrouter": "openrouter/free",
            "groq": "llama-3.3-70b-versatile",
            "ollama": "llama3.2",
        }
        if provider not in defaults:
            raise ConfigurationError(f"Unsupported LLM_PROVIDER: {provider}")
        model = os.getenv("LLM_MODEL", defaults.get(provider, "")).strip()
        if not model:
            raise ConfigurationError(f"LLM_MODEL is not configured for {provider}")
        search_provider = os.getenv("SEARCH_PROVIDER", "tavily").strip().lower()
        if search_provider != "tavily":
            raise ConfigurationError(f"Unsupported SEARCH_PROVIDER: {search_provider}")
        return cls(
            llm_provider=provider,
            llm_model=model,
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY", "").strip() or None,
            groq_api_key=os.getenv("GROQ_API_KEY", "").strip() or None,
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/"),
            ollama_model=os.getenv("OLLAMA_MODEL", model).strip(),
            search_provider=search_provider,
            tavily_api_key=os.getenv("TAVILY_API_KEY", "").strip() or None,
            search_max_results=max_results,
            search_evidence_max_chars=evidence_max_chars,
        )

    def llm_api_key(self) -> str | None:
        if self.llm_provider == "openrouter":
            return self.openrouter_api_key
        if self.llm_provider == "groq":
            return self.groq_api_key
        return None


def require_llm_settings(settings: Settings) -> None:
    if settings.llm_provider in {"openrouter", "groq"} and not settings.llm_api_key():
        variable = "OPENROUTER_API_KEY" if settings.llm_provider == "openrouter" else "GROQ_API_KEY"
        raise ConfigurationError(f"{variable} is not configured")


def require_search_settings(settings: Settings) -> None:
    if settings.search_provider == "tavily" and not settings.tavily_api_key:
        raise ConfigurationError("TAVILY_API_KEY is not configured")
