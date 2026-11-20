"""Application settings, read from environment variables and the local `.env` file.

Secrets are typed as `SecretStr` so they never appear in reprs, logs or tracebacks.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ThinkingLevel = Literal["low", "medium", "high", "xhigh"]


class RateLimits(BaseModel):
    """Free-tier limits for one model. `None` means not yet confirmed from AI Studio.

    Override from the environment with e.g. `GENERATION_LIMITS__REQUESTS_PER_MINUTE=10`.
    """

    requests_per_minute: int | None = Field(default=None, gt=0)
    tokens_per_minute: int | None = Field(default=None, gt=0)
    requests_per_day: int | None = Field(default=None, gt=0)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        env_ignore_empty=True,
        extra="ignore",
    )

    # Decision model (scope check, re-rank, support check).
    decision_provider: Literal["gemini"] = "gemini"
    decision_model: str = "gemini-decision-1"
    decision_budget_usd: float = Field(default=0.0, ge=0)
    decision_usd_per_million_input_tokens: float = Field(default=0.0, ge=0)

    # Generative model (answers, judge) and embeddings.
    gemini_api_key: SecretStr
    generation_model: str = "gemini-3.5-flash-lite"
    generation_thinking_level: ThinkingLevel = "low"
    # Judge: a different model family from the generator, so it does not favour its style.
    judge_model: str = "gemma-4-31b-it"
    embedding_model: str = "gemini-embedding-2"
    embedding_dimensions: int = 768

    # Free-tier limits; filled in from AI Studio (see docs/providers.md).
    decision_limits: RateLimits = RateLimits(
        requests_per_minute=200, tokens_per_minute=50_000, requests_per_day=10_000
    )
    generation_limits: RateLimits = RateLimits(
        requests_per_minute=15, tokens_per_minute=250_000, requests_per_day=500
    )
    # Gemma: 30 RPM, 16K TPM, 14.4K RPD; tokens per minute is the limit that binds.
    judge_limits: RateLimits = RateLimits(
        requests_per_minute=30, tokens_per_minute=16_000, requests_per_day=14_400
    )
    embedding_limits: RateLimits = RateLimits(
        requests_per_minute=100, tokens_per_minute=30_000, requests_per_day=1_000
    )
    max_rate_limit_retries: int = Field(default=3, ge=0)  # D55; also covers 5xx

    # Observability and storage.
    langfuse_public_key: SecretStr
    langfuse_secret_key: SecretStr
    langfuse_host: str = "https://cloud.langfuse.com"
    database_url: SecretStr

    # Public web API (D64). The daily cap leaves generator quota (about 2 calls per ask) for evals.
    demo_daily_cap: int = Field(default=150, gt=0)
    asks_per_ip_per_hour: int = Field(default=10, gt=0)
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Local state: response cache and cost/quota ledger.
    state_dir: Path = Path(".state")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load settings once per process."""
    return Settings()  # type: ignore[call-arg]  # required fields come from the environment
