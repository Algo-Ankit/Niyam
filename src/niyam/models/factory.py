"""Builds the configured model stack: `Cached(Metered(ProviderAdapter))` for each role.

This is the only module that chooses providers. Adding a provider (for example Jev as a
second decision model) means adding an adapter and one branch in `_decision_adapter`.
"""

from dataclasses import dataclass

from google import genai

from niyam.config import Settings
from niyam.models.cache import ResponseCache
from niyam.models.cached import CachedDecisionModel, CachedEmbedder, CachedGenerativeModel
from niyam.models.gemini import GeminiDecisionModel, GeminiEmbedder, GeminiGenerativeModel
from niyam.models.interfaces import DecisionModel, Embedder, GenerativeModel
from niyam.models.ledger import CostLedger
from niyam.models.metering import (
    Meter,
    MeteredDecisionModel,
    MeteredEmbedder,
    MeteredGenerativeModel,
)

# Bump to invalidate every cached response, e.g. after changing how responses are parsed.
CACHE_VERSION = "1"
GEMINI = "gemini"


@dataclass
class ModelSuite:
    decision: DecisionModel
    generator: GenerativeModel
    judge: GenerativeModel
    embedder: Embedder
    ledger: CostLedger
    cache: ResponseCache

    def close(self) -> None:
        self.cache.close()
        self.ledger.close()


def build_models(settings: Settings, *, use_cache: bool = True) -> ModelSuite:
    ledger = CostLedger(settings.state_dir / "ledger.sqlite")
    cache = ResponseCache(settings.state_dir / "cache.sqlite")
    api_key = settings.gemini_api_key.get_secret_value()
    client = genai.Client(api_key=api_key)

    decision: DecisionModel = MeteredDecisionModel(
        _decision_adapter(settings, api_key),
        Meter(
            settings.decision_provider,
            settings.decision_model,
            settings.decision_limits,
            ledger,
            budget_usd=settings.decision_budget_usd,
            usd_per_million_input_tokens=settings.decision_usd_per_million_input_tokens,
            max_retries=settings.max_rate_limit_retries,
        ),
    )
    generator: GenerativeModel = MeteredGenerativeModel(
        GeminiGenerativeModel(client, settings.generation_model),
        Meter(
            GEMINI,
            settings.generation_model,
            settings.generation_limits,
            ledger,
            max_retries=settings.max_rate_limit_retries,
        ),
    )
    judge: GenerativeModel = MeteredGenerativeModel(
        GeminiGenerativeModel(client, settings.judge_model),
        Meter(
            GEMINI,
            settings.judge_model,
            settings.judge_limits,
            ledger,
            max_retries=settings.max_rate_limit_retries,
        ),
    )
    embedder: Embedder = MeteredEmbedder(
        GeminiEmbedder(client, settings.embedding_model, settings.embedding_dimensions),
        Meter(
            GEMINI,
            settings.embedding_model,
            settings.embedding_limits,
            ledger,
            max_retries=settings.max_rate_limit_retries,
        ),
    )

    if use_cache:
        decision = CachedDecisionModel(decision, cache, settings.decision_provider, CACHE_VERSION)
        generator = CachedGenerativeModel(generator, cache, GEMINI, CACHE_VERSION)
        judge = CachedGenerativeModel(judge, cache, GEMINI, CACHE_VERSION)
        embedder = CachedEmbedder(embedder, cache, GEMINI, CACHE_VERSION)
    return ModelSuite(decision, generator, judge, embedder, ledger, cache)


def _decision_adapter(settings: Settings, api_key: str) -> DecisionModel:
    match settings.decision_provider:
        case "gemini":
            # The Decisions API is served on v1beta.
            client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
            return GeminiDecisionModel(client, settings.decision_model)
