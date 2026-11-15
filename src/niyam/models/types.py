"""Provider-neutral request and result types shared by every model adapter."""

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel

from niyam.config import ThinkingLevel

EmbeddingPurpose = Literal["document", "query"]


@dataclass(frozen=True, slots=True)
class Usage:
    """Token usage reported by the provider for one request."""

    input_tokens: int = 0
    output_tokens: int = 0
    thought_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.thought_tokens


@dataclass(frozen=True, slots=True)
class DecisionResult:
    """Yes-probabilities keyed by question name, in [0, 1]."""

    probabilities: dict[str, float]
    usage: Usage


@dataclass(frozen=True, slots=True)
class GenerationResult[T: BaseModel]:
    """A structured generation, already validated against its schema."""

    output: T
    usage: Usage


@dataclass(frozen=True, slots=True)
class EmbeddingInput:
    """One text to embed. `title` gives a document its context (e.g. its hierarchy path)."""

    text: str
    purpose: EmbeddingPurpose
    title: str | None = None


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    vectors: list[list[float]]
    usage: Usage = field(default_factory=Usage)


@dataclass(frozen=True, slots=True)
class GenerationRequest[T: BaseModel]:
    prompt: str
    schema: type[T]
    thinking_level: ThinkingLevel | None  # None for models without thinking levels (Gemma)
