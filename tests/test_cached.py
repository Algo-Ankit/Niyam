from pathlib import Path

import pytest
from pydantic import BaseModel

from fakes import FakeDecisionModel, FakeEmbedder, FakeGenerativeModel
from niyam.models.cache import ResponseCache
from niyam.models.cached import CachedDecisionModel, CachedEmbedder, CachedGenerativeModel
from niyam.models.types import EmbeddingInput, GenerationRequest


class Echo(BaseModel):
    answer: str


@pytest.fixture
def cache(tmp_path: Path) -> ResponseCache:
    return ResponseCache(tmp_path / "cache.sqlite")


def test_decision_hit_skips_the_model(cache: ResponseCache) -> None:
    fake = FakeDecisionModel()
    model = CachedDecisionModel(fake, cache, "p", "v1")
    first = model.decide("state", {"a": "?", "b": "?"})
    second = model.decide("state", {"b": "?", "a": "?"})
    assert fake.calls == 1
    assert second == first


def test_decision_version_bump_misses(cache: ResponseCache) -> None:
    fake = FakeDecisionModel()
    CachedDecisionModel(fake, cache, "p", "v1").decide("s", {"a": "?"})
    CachedDecisionModel(fake, cache, "p", "v2").decide("s", {"a": "?"})
    assert fake.calls == 2


def test_generation_hit_returns_validated_model(cache: ResponseCache) -> None:
    fake = FakeGenerativeModel()
    model = CachedGenerativeModel(fake, cache, "p", "v1")
    request = GenerationRequest("hello", Echo, "low")
    model.generate(request)
    hit = model.generate(request)
    assert fake.calls == 1
    assert isinstance(hit.output, Echo)
    assert hit.output.answer == "echo: hello"


def test_generation_thinking_level_is_part_of_the_key(cache: ResponseCache) -> None:
    fake = FakeGenerativeModel()
    model = CachedGenerativeModel(fake, cache, "p", "v1")
    model.generate(GenerationRequest("hello", Echo, "low"))
    model.generate(GenerationRequest("hello", Echo, "medium"))
    assert fake.calls == 2


def test_embedder_sends_only_unseen_texts_and_keeps_order(cache: ResponseCache) -> None:
    fake = FakeEmbedder()
    model = CachedEmbedder(fake, cache, "p", "v1")
    a = EmbeddingInput("a", "document", "T")
    bbb = EmbeddingInput("bbb", "document", "T")
    cc = EmbeddingInput("cc", "query")
    model.embed([a, bbb])

    result = model.embed([cc, a, bbb])
    assert fake.batches == [["a", "bbb"], ["cc"]]
    assert result.vectors == [[2.0, 1.0], [1.0, 1.0], [3.0, 1.0]]


def test_embedder_purpose_is_part_of_the_key(cache: ResponseCache) -> None:
    fake = FakeEmbedder()
    model = CachedEmbedder(fake, cache, "p", "v1")
    model.embed([EmbeddingInput("x", "document")])
    model.embed([EmbeddingInput("x", "query")])
    assert len(fake.batches) == 2
