"""The three model roles. Pipeline code depends only on these, never on a provider SDK.

Switching provider means adding an adapter that satisfies one of these protocols and
selecting it in configuration (see `niyam.models.factory`).
"""

from collections.abc import Mapping, Sequence
from typing import Protocol

from pydantic import BaseModel

from niyam.models.types import (
    DecisionResult,
    EmbeddingInput,
    EmbeddingResult,
    GenerationRequest,
    GenerationResult,
)


class DecisionModel(Protocol):
    """Answers yes/no questions about one shared input with calibrated probabilities."""

    @property
    def model_id(self) -> str: ...

    def decide(self, state: str, questions: Mapping[str, str]) -> DecisionResult:
        """Return P(yes) for each question, keyed by the question's name.

        All questions are asked against the same `state` in a single request.
        """
        ...


class GenerativeModel(Protocol):
    """Writes text constrained to a JSON schema."""

    @property
    def model_id(self) -> str: ...

    def generate[T: BaseModel](self, request: GenerationRequest[T]) -> GenerationResult[T]: ...


class Embedder(Protocol):
    """Turns texts into unit-length vectors, one vector per input, in input order."""

    @property
    def model_id(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    def embed(self, inputs: Sequence[EmbeddingInput]) -> EmbeddingResult: ...
