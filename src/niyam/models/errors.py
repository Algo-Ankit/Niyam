"""Errors raised by the model layer. Adapters translate provider errors into these."""


class ModelError(Exception):
    """Base class for model-layer failures."""


class RateLimitedError(ModelError):
    """The provider rejected the request with HTTP 429."""

    def __init__(self, message: str, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class ProviderUnavailableError(ModelError):
    """The provider failed temporarily (HTTP 5xx, e.g. 503 high demand); a retry may succeed."""


class QuotaExhaustedError(ModelError):
    """A local daily request quota has been reached; calling would exceed the free tier."""


class BudgetExceededError(ModelError):
    """A call would push spend for a provider past its configured USD budget."""


class ProviderResponseError(ModelError):
    """The provider answered, but the response is missing data or has an unexpected shape."""
