"""Gemini API adapters for the three model roles.

Behaviours verified against live calls on 2026-11-14 (see docs/providers.md):
- Decisions return answers keyed by question name in arbitrary order; `noul` is P(yes).
- Generation models (gemini-3.5-flash-lite by default) are called through the Interactions API
  with `thinking_level`.
- gemini-embedding-2 aggregates a plain list of strings into ONE vector; each text must be
  wrapped in its own `Content` to get one vector per text. It has no `task_type`; the task
  is expressed with documented text prefixes.
"""

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any, Literal, cast

from google import genai
from google.genai import errors, types
from google.genai._gaos.lib import compat_errors
from pydantic import BaseModel, ConfigDict, ValidationError

from niyam.models.errors import ProviderResponseError, ProviderUnavailableError, RateLimitedError
from niyam.models.ratelimit import estimate_tokens
from niyam.models.types import (
    DecisionResult,
    EmbeddingInput,
    EmbeddingResult,
    GenerationRequest,
    GenerationResult,
    Usage,
)

HTTP_TOO_MANY_REQUESTS = 429
HTTP_SERVER_ERRORS = range(500, 600)  # Google's troubleshooting page: retry 5xx (D55)
EMBEDDING_MAX_INPUT_TOKENS = 8192  # documented limit; longer input is silently truncated


class _Boundary(BaseModel):
    """Our own view of an SDK response. The SDK's typed models live in a private package,
    so responses are validated into these instead of importing SDK internals."""

    model_config = ConfigDict(from_attributes=True, extra="ignore")


class _NoulAnswer(_Boundary):
    type: Literal["noul"]
    noul: float


class _DecisionUsage(_Boundary):
    total_input_tokens: int


class _DecisionResponse(_Boundary):
    answers: dict[str, _NoulAnswer]
    usage: _DecisionUsage


class _InteractionUsage(_Boundary):
    # The SDK reports absent counts as None (e.g. no thinking), so None is accepted here.
    total_input_tokens: int | None = None
    total_output_tokens: int | None = None
    total_thought_tokens: int | None = None


class _Interaction(_Boundary):
    output_text: str
    usage: _InteractionUsage


def _validated[B: _Boundary](boundary: type[B], response: object, model_id: str) -> B:
    try:
        return boundary.model_validate(response, from_attributes=True)
    except ValidationError as error:
        raise ProviderResponseError(f"{model_id}: unexpected response shape") from error


# NOTE: the Interactions API (generation) raises compat_errors from a private SDK package, not
# errors.APIError (google-genai 3.3.0). Tests build one, so a moved module fails loudly.
@contextmanager
def _transient_errors_translated(model_id: str) -> Iterator[None]:
    try:
        yield
    except errors.APIError as error:
        _raise_if_transient(model_id, error.code, error)
        raise
    except compat_errors.APIStatusError as error:
        _raise_if_transient(model_id, error.status_code, error)
        raise


def _raise_if_transient(model_id: str, status: int | None, error: Exception) -> None:
    if status == HTTP_TOO_MANY_REQUESTS:
        raise RateLimitedError(f"{model_id}: rate limited by the Gemini API") from error
    if status in HTTP_SERVER_ERRORS:
        raise ProviderUnavailableError(f"{model_id}: Gemini API error {status}") from error


class GeminiDecisionModel:
    def __init__(self, client: genai.Client, model_id: str) -> None:
        self._client = client
        self._model_id = model_id

    @property
    def model_id(self) -> str:
        return self._model_id

    def decide(self, state: str, questions: Mapping[str, str]) -> DecisionResult:
        if not questions:
            raise ValueError("at least one question is required")
        payload = {name: {"type": "noul", "instructions": text} for name, text in questions.items()}
        with _transient_errors_translated(self._model_id):
            raw = self._client.decisions.create(
                model=self._model_id,
                input=state,
                # The SDK's request TypedDicts are private; payload follows the documented shape.
                questions=cast(Any, payload),
            )
        response = _validated(_DecisionResponse, raw, self._model_id)
        missing = set(questions) - set(response.answers)
        if missing:
            raise ProviderResponseError(f"{self._model_id}: no answer for {sorted(missing)}")
        probabilities = {name: response.answers[name].noul for name in questions}
        return DecisionResult(probabilities, Usage(input_tokens=response.usage.total_input_tokens))


class GeminiGenerativeModel:
    def __init__(self, client: genai.Client, model_id: str) -> None:
        self._client = client
        self._model_id = model_id

    @property
    def model_id(self) -> str:
        return self._model_id

    def generate[T: BaseModel](self, request: GenerationRequest[T]) -> GenerationResult[T]:
        # NOTE: Gemma models reject `thinking_level` (HTTP 400), so it is sent only when set.
        thinking: dict[str, Any] = (
            {}
            if request.thinking_level is None
            else {"generation_config": {"thinking_level": request.thinking_level}}
        )
        with _transient_errors_translated(self._model_id):
            raw = self._client.interactions.create(
                model=self._model_id,
                input=request.prompt,
                **thinking,
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": request.schema.model_json_schema(),
                },
            )
        interaction = _validated(_Interaction, raw, self._model_id)
        try:
            output = request.schema.model_validate_json(interaction.output_text)
        except ValidationError as error:
            raise ProviderResponseError(
                f"{self._model_id}: output does not match {request.schema.__name__}"
            ) from error
        usage = interaction.usage
        return GenerationResult(
            output,
            Usage(
                input_tokens=usage.total_input_tokens or 0,
                output_tokens=usage.total_output_tokens or 0,
                thought_tokens=usage.total_thought_tokens or 0,
            ),
        )


class GeminiEmbedder:
    def __init__(self, client: genai.Client, model_id: str, dimensions: int) -> None:
        self._client = client
        self._model_id = model_id
        self._dimensions = dimensions

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, inputs: Sequence[EmbeddingInput]) -> EmbeddingResult:
        if not inputs:
            return EmbeddingResult([])
        texts = [_format_for_embedding(item) for item in inputs]
        too_long = [
            i for i, t in enumerate(texts) if estimate_tokens(t) > EMBEDDING_MAX_INPUT_TOKENS
        ]
        if too_long:
            raise ValueError(f"inputs {too_long} exceed {EMBEDDING_MAX_INPUT_TOKENS} tokens")

        with _transient_errors_translated(self._model_id):
            response = self._client.models.embed_content(
                model=self._model_id,
                contents=[types.Content(parts=[types.Part.from_text(text=t)]) for t in texts],
                config=types.EmbedContentConfig(output_dimensionality=self._dimensions),
            )
        vectors = [list(e.values or []) for e in response.embeddings or []]
        if len(vectors) != len(inputs):
            raise ProviderResponseError(
                f"{self._model_id}: {len(vectors)} vectors returned for {len(inputs)} inputs"
            )
        if any(len(v) != self._dimensions for v in vectors):
            raise ProviderResponseError(f"{self._model_id}: unexpected vector dimension")
        tokens = response.usage_metadata.prompt_token_count if response.usage_metadata else 0
        return EmbeddingResult(vectors, Usage(input_tokens=int(tokens or 0)))


def _format_for_embedding(item: EmbeddingInput) -> str:
    """Apply the task prefixes documented for gemini-embedding-2 retrieval."""
    if item.purpose == "query":
        return f"task: search result | query: {item.text}"
    return f"title: {item.title or 'none'} | text: {item.text}"
