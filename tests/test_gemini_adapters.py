"""Adapter tests against stub SDK clients shaped like the responses seen in live probes."""

from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from google.genai import errors
from google.genai._gaos.lib import compat_errors
from pydantic import BaseModel

from niyam.config import ThinkingLevel
from niyam.models.errors import ProviderResponseError, ProviderUnavailableError, RateLimitedError
from niyam.models.gemini import GeminiDecisionModel, GeminiEmbedder, GeminiGenerativeModel
from niyam.models.types import EmbeddingInput, GenerationRequest


def stub_client(**services: Any) -> Any:
    return SimpleNamespace(**services)


def answer(p: float) -> SimpleNamespace:
    return SimpleNamespace(noul=p, confidence=max(p, 1 - p), type="noul")


def test_decision_reads_answers_by_name_not_position() -> None:
    sent: dict[str, Any] = {}

    def create(**kwargs: Any) -> SimpleNamespace:
        sent.update(kwargs)
        # Live responses come back in arbitrary key order.
        return SimpleNamespace(
            answers={"b": answer(0.2), "a": answer(0.9)},
            usage=SimpleNamespace(total_input_tokens=141),
        )

    model = GeminiDecisionModel(stub_client(decisions=SimpleNamespace(create=create)), "d1")
    result = model.decide("state", {"a": "Is A?", "b": "Is B?"})

    assert result.probabilities == {"a": 0.9, "b": 0.2}
    assert result.usage.input_tokens == 141
    assert sent["questions"]["a"] == {"type": "noul", "instructions": "Is A?"}


def test_decision_missing_answer_is_an_error() -> None:
    def create(**_: Any) -> SimpleNamespace:
        return SimpleNamespace(
            answers={"a": answer(0.9)}, usage=SimpleNamespace(total_input_tokens=1)
        )

    model = GeminiDecisionModel(stub_client(decisions=SimpleNamespace(create=create)), "d1")
    with pytest.raises(ProviderResponseError, match="'b'"):
        model.decide("s", {"a": "?", "b": "?"})


def test_decision_non_yes_no_answer_is_rejected_at_the_boundary() -> None:
    def create(**_: Any) -> SimpleNamespace:
        refusal = SimpleNamespace(type="refusal")
        return SimpleNamespace(answers={"a": refusal}, usage=SimpleNamespace(total_input_tokens=1))

    model = GeminiDecisionModel(stub_client(decisions=SimpleNamespace(create=create)), "d1")
    with pytest.raises(ProviderResponseError, match="unexpected response shape"):
        model.decide("s", {"a": "?"})


def test_http_429_becomes_rate_limited_error() -> None:
    def create(**_: Any) -> None:
        raise errors.ClientError(429, {"error": {"message": "quota"}}, httpx.Response(429))

    model = GeminiDecisionModel(stub_client(decisions=SimpleNamespace(create=create)), "d1")
    with pytest.raises(RateLimitedError):
        model.decide("s", {"a": "?"})


def test_other_api_errors_propagate_unchanged() -> None:
    def create(**_: Any) -> None:
        raise errors.ClientError(400, {"error": {"message": "bad"}}, httpx.Response(400))

    model = GeminiDecisionModel(stub_client(decisions=SimpleNamespace(create=create)), "d1")
    with pytest.raises(errors.ClientError):
        model.decide("s", {"a": "?"})


def test_http_5xx_becomes_provider_unavailable_error() -> None:
    def create(**_: Any) -> None:
        raise errors.ServerError(503, {"error": {"message": "busy"}}, httpx.Response(503))

    model = GeminiDecisionModel(stub_client(decisions=SimpleNamespace(create=create)), "d1")
    with pytest.raises(ProviderUnavailableError):
        model.decide("s", {"a": "?"})


def interactions_raising(status: int) -> Any:
    response = httpx.Response(status, request=httpx.Request("POST", "https://example.test"))

    def create(**_: Any) -> None:
        raise compat_errors.APIStatusError("error", response=response, body=None)

    return SimpleNamespace(create=create)


@pytest.mark.parametrize(
    ("status", "expected"), [(429, RateLimitedError), (503, ProviderUnavailableError)]
)
def test_interactions_api_errors_are_translated(status: int, expected: type[Exception]) -> None:
    client = stub_client(interactions=interactions_raising(status))
    with pytest.raises(expected):
        GeminiGenerativeModel(client, "h").generate(GenerationRequest("p", Answer, "low"))


def test_interactions_api_client_errors_propagate_unchanged() -> None:
    client = stub_client(interactions=interactions_raising(400))
    with pytest.raises(compat_errors.APIStatusError):
        GeminiGenerativeModel(client, "h").generate(GenerationRequest("p", Answer, "low"))


class Answer(BaseModel):
    answer: str


def interactions_returning(text: str, sent: dict[str, Any] | None = None) -> Any:
    usage = SimpleNamespace(
        total_input_tokens=400, total_output_tokens=80, total_thought_tokens=100
    )
    response = SimpleNamespace(output_text=text, usage=usage)

    def create(**kwargs: Any) -> SimpleNamespace:
        if sent is not None:
            sent.update(kwargs)
        return response

    return SimpleNamespace(create=create)


def test_generation_parses_schema_and_usage() -> None:
    client = stub_client(interactions=interactions_returning('{"answer": "Rs 2,00,000"}'))
    result = GeminiGenerativeModel(client, "h").generate(GenerationRequest("p", Answer, "low"))
    assert result.output.answer == "Rs 2,00,000"
    assert (result.usage.input_tokens, result.usage.thought_tokens) == (400, 100)


def test_thinking_level_is_sent_only_when_set() -> None:
    with_level: dict[str, Any] = {}
    without: dict[str, Any] = {}
    levels: list[tuple[dict[str, Any], ThinkingLevel | None]] = [
        (with_level, "low"),
        (without, None),
    ]
    for sent, level in levels:
        client = stub_client(interactions=interactions_returning('{"answer": "x"}', sent))
        GeminiGenerativeModel(client, "m").generate(GenerationRequest("p", Answer, level))
    assert with_level["generation_config"] == {"thinking_level": "low"}
    assert "generation_config" not in without


def test_generation_invalid_json_is_a_provider_error() -> None:
    client = stub_client(interactions=interactions_returning('{"wrong": 1}'))
    with pytest.raises(ProviderResponseError):
        GeminiGenerativeModel(client, "h").generate(GenerationRequest("p", Answer, "low"))


def embed_client(vectors: list[list[float]], sent: dict[str, Any]) -> Any:
    def embed_content(**kwargs: Any) -> SimpleNamespace:
        sent.update(kwargs)
        return SimpleNamespace(
            embeddings=[SimpleNamespace(values=v) for v in vectors],
            usage_metadata=SimpleNamespace(prompt_token_count=109),
        )

    return stub_client(models=SimpleNamespace(embed_content=embed_content))


def test_embedder_wraps_each_text_and_applies_task_prefixes() -> None:
    sent: dict[str, Any] = {}
    embedder = GeminiEmbedder(embed_client([[1.0, 0.0], [0.0, 1.0]], sent), "e2", 2)
    result = embedder.embed(
        [EmbeddingInput("clause text", "document", "PPI > 9.1"), EmbeddingInput("q?", "query")]
    )
    texts = [c.parts[0].text for c in sent["contents"]]
    assert texts == ["title: PPI > 9.1 | text: clause text", "task: search result | query: q?"]
    assert result.vectors == [[1.0, 0.0], [0.0, 1.0]]
    assert result.usage.input_tokens == 109


def test_embedder_rejects_an_aggregated_response() -> None:
    # gemini-embedding-2 returns ONE vector if texts are not wrapped separately.
    embedder = GeminiEmbedder(embed_client([[1.0, 0.0]], {}), "e2", 2)
    with pytest.raises(ProviderResponseError, match="1 vectors returned for 2 inputs"):
        embedder.embed([EmbeddingInput("a", "document"), EmbeddingInput("b", "document")])


def test_embedder_rejects_wrong_dimension() -> None:
    embedder = GeminiEmbedder(embed_client([[1.0, 0.0, 0.0]], {}), "e2", 2)
    with pytest.raises(ProviderResponseError, match="dimension"):
        embedder.embed([EmbeddingInput("a", "document")])


def test_embedder_rejects_input_that_would_be_truncated() -> None:
    embedder = GeminiEmbedder(embed_client([], {}), "e2", 2)
    with pytest.raises(ValueError, match="exceed"):
        embedder.embed([EmbeddingInput("x" * 40_000, "document")])
