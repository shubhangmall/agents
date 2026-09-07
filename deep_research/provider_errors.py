class ProviderError(RuntimeError):
    """Base class for sanitized provider failures."""

    category = "provider error"

    def __init__(self, message: str):
        super().__init__(message)


class ProviderConfigurationError(ProviderError):
    category = "authentication/configuration failure"


class ProviderRateLimitError(ProviderError):
    category = "rate limit"


class ProviderUnavailableError(ProviderError):
    category = "provider unavailable"


class UnsupportedProviderCapabilityError(ProviderError):
    category = "unsupported provider capability"


class StructuredOutputError(ProviderError):
    category = "structured-output failure"


class SearchProviderError(ProviderError):
    category = "search-provider failure"


class WriterStreamError(ProviderError):
    category = "interrupted writer stream"
