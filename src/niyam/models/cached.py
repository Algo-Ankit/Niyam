"""Cache-first wrappers for each model role.

Compose them outermost (`Cached(Metered(Adapter))`) so a cache hit never consumes rate
limit or quota and is never recorded in the ledger.
"""

from collections.abc import Mapping, Sequence
from dataclasses import asdict
from typing import Any

from pydantic import BaseModel

from niyam.models.cache import ResponseCache, cache_key
from niyam.models.interfaces import DecisionModel, Embedder, GenerativeModel
from niyam.models.types import (
    DecisionResult,
    EmbeddingInput,
    EmbeddingResult,
    GenerationRequest,
    GenerationResult,
    Usage,
)


class CachedDecisionModel:
    def __init__(self, inner: DecisionModel, cache: ResponseCache, provider: str, version: str):
        self._inner = inner
        self._cache = cache
        self._provider = provider
        self._version = version

    @property
    def model_id(self) -> str:
        return self._inner.model_id

    def decide(self, state: str, questions: Mapping[str, str]) -> DecisionResult:
        key = cache_key(
            self._provider,
            self.model_id,
            self._version,
            {"state": state, "questions": dict(questions)},
        )
        if (hit := self._cache.get(key)) is not None:
            return DecisionResult(hit["probabilities"], Usage(**hit["usage"]))
        result = self._inner.decide(state, questions)
        self._cache.put(key, {"probabilities": result.probabilities, "usage": asdict(result.usage)})
        return result


class CachedGenerativeModel:
    def __init__(self, inner: GenerativeModel, cache: ResponseCache, provider: str, version: str):
        self._inner = inner
        self._cache = cache
        self._provider = provider
        self._version = version

    @property
    def model_id(self) -> str:
        return self._inner.model_id

    def generate[T: BaseModel](self, request: GenerationRequest[T]) -> GenerationResult[T]:
        key = cache_key(
            self._provider,
            self.model_id,
            self._version,
            {
                "prompt": request.prompt,
                "schema": request.schema.model_json_schema(),
                "thinking_level": request.thinking_level,
            },
        )
        if (hit := self._cache.get(key)) is not None:
            return GenerationResult(
                request.schema.model_validate(hit["output"]), Usage(**hit["usage"])
            )
        result = self._inner.generate(request)
        self._cache.put(
            key, {"output": result.output.model_dump(mode="json"), "usage": asdict(result.usage)}
        )
        return result


class CachedEmbedder:
    """Caches each vector separately, so only texts never seen before are sent to the provider."""

    def __init__(self, inner: Embedder, cache: ResponseCache, provider: str, version: str):
        self._inner = inner
        self._cache = cache
        self._provider = provider
        self._version = version

    @property
    def model_id(self) -> str:
        return self._inner.model_id

    @property
    def dimensions(self) -> int:
        return self._inner.dimensions

    def embed(self, inputs: Sequence[EmbeddingInput]) -> EmbeddingResult:
        keys = [self._key(item) for item in inputs]
        vectors: list[list[float] | None] = [self._cache.get(k) for k in keys]
        missing = [i for i, v in enumerate(vectors) if v is None]
        usage = Usage()
        if missing:
            fresh = self._inner.embed([inputs[i] for i in missing])
            usage = fresh.usage
            for i, vector in zip(missing, fresh.vectors, strict=True):
                self._cache.put(keys[i], vector)
                vectors[i] = vector
        return EmbeddingResult([v for v in vectors if v is not None], usage)

    def _key(self, item: EmbeddingInput) -> str:
        payload: dict[str, Any] = asdict(item) | {"dimensions": self.dimensions}
        return cache_key(self._provider, self.model_id, self._version, payload)
