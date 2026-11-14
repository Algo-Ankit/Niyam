"""In-memory model fakes for unit tests. They count calls so tests can assert on caching."""

from collections.abc import Mapping, Sequence

from pydantic import BaseModel

from niyam.models.types import (
    DecisionResult,
    EmbeddingInput,
    EmbeddingResult,
    GenerationRequest,
    GenerationResult,
    Usage,
)


class FakeDecisionModel:
    model_id = "fake-decision"

    def __init__(self, probability: float = 0.9) -> None:
        self.calls = 0
        self._probability = probability

    def decide(self, state: str, questions: Mapping[str, str]) -> DecisionResult:
        self.calls += 1
        return DecisionResult(
            {name: self._probability for name in questions}, Usage(input_tokens=len(state))
        )


class FakeGenerativeModel:
    model_id = "fake-generator"

    def __init__(self) -> None:
        self.calls = 0

    def generate[T: BaseModel](self, request: GenerationRequest[T]) -> GenerationResult[T]:
        self.calls += 1
        output = request.schema.model_validate({"answer": f"echo: {request.prompt}"})
        return GenerationResult(output, Usage(input_tokens=5, output_tokens=3, thought_tokens=2))


class FakeEmbedder:
    model_id = "fake-embedder"
    dimensions = 2

    def __init__(self) -> None:
        self.batches: list[list[str]] = []

    def embed(self, inputs: Sequence[EmbeddingInput]) -> EmbeddingResult:
        self.batches.append([i.text for i in inputs])
        return EmbeddingResult(
            [[float(len(i.text)), 1.0] for i in inputs], Usage(input_tokens=len(inputs))
        )
