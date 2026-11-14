"""Quota, budget and rate-limit enforcement around every live model call.

`Meter` holds the policy for one model; the `Metered*` wrappers apply it to each model role
without the adapters knowing about limits, retries or cost.
"""

import time
from collections.abc import Callable, Mapping, Sequence

from pydantic import BaseModel

from niyam.config import RateLimits
from niyam.models.errors import BudgetExceededError, QuotaExhaustedError, RateLimitedError
from niyam.models.interfaces import DecisionModel, Embedder, GenerativeModel
from niyam.models.ledger import CostLedger
from niyam.models.ratelimit import SlidingWindowLimiter, estimate_tokens
from niyam.models.types import (
    DecisionResult,
    EmbeddingInput,
    EmbeddingResult,
    GenerationRequest,
    GenerationResult,
    Usage,
)

BACKOFF_BASE_SECONDS = 2.0


class Meter:
    def __init__(  # noqa: PLR0913 (each argument is an independent policy input)
        self,
        provider: str,
        model_id: str,
        limits: RateLimits,
        ledger: CostLedger,
        *,
        budget_usd: float | None = None,
        usd_per_million_input_tokens: float = 0.0,
        max_retries: int = 0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.provider = provider
        self.model_id = model_id
        self._limits = limits
        self._ledger = ledger
        self._budget_usd = budget_usd
        self._price = usd_per_million_input_tokens / 1_000_000
        self._max_retries = max_retries
        self._sleep = sleep
        self._limiter = SlidingWindowLimiter(
            limits.requests_per_minute, limits.tokens_per_minute, sleep=sleep
        )

    def run[R](
        self, estimated_tokens: int, call: Callable[[], R], usage_of: Callable[[R], Usage]
    ) -> R:
        self._check_daily_quota()
        self._check_budget(estimated_tokens * self._price)
        for attempt in range(self._max_retries + 1):
            self._limiter.acquire(estimated_tokens)
            try:
                result = call()
            except RateLimitedError as error:
                # A rejected request may still count against the provider's daily quota.
                self._ledger.record(self.provider, self.model_id, Usage(), 0.0)
                if attempt == self._max_retries:
                    raise
                self._sleep(error.retry_after_seconds or BACKOFF_BASE_SECONDS * 2**attempt)
            else:
                usage = usage_of(result)
                self._ledger.record(
                    self.provider, self.model_id, usage, usage.input_tokens * self._price
                )
                return result
        raise AssertionError("unreachable: the loop returns or raises")

    def _check_daily_quota(self) -> None:
        limit = self._limits.requests_per_day
        if limit is not None and self._ledger.requests_today(self.model_id) >= limit:
            raise QuotaExhaustedError(f"{self.model_id}: daily limit of {limit} requests reached")

    def _check_budget(self, estimated_cost: float) -> None:
        if self._budget_usd is None:
            return
        spent = self._ledger.spend_usd(self.provider)
        if spent + estimated_cost > self._budget_usd:
            raise BudgetExceededError(
                f"{self.provider}: spent {spent:.6f} USD, call would exceed the "
                f"{self._budget_usd:.2f} USD budget"
            )


class MeteredDecisionModel:
    def __init__(self, inner: DecisionModel, meter: Meter) -> None:
        self._inner = inner
        self._meter = meter

    @property
    def model_id(self) -> str:
        return self._inner.model_id

    def decide(self, state: str, questions: Mapping[str, str]) -> DecisionResult:
        estimate = estimate_tokens(state + "".join(questions.values()))
        return self._meter.run(
            estimate, lambda: self._inner.decide(state, questions), lambda r: r.usage
        )


class MeteredGenerativeModel:
    def __init__(self, inner: GenerativeModel, meter: Meter) -> None:
        self._inner = inner
        self._meter = meter

    @property
    def model_id(self) -> str:
        return self._inner.model_id

    def generate[T: BaseModel](self, request: GenerationRequest[T]) -> GenerationResult[T]:
        return self._meter.run(
            estimate_tokens(request.prompt),
            lambda: self._inner.generate(request),
            lambda r: r.usage,
        )


class MeteredEmbedder:
    def __init__(self, inner: Embedder, meter: Meter) -> None:
        self._inner = inner
        self._meter = meter

    @property
    def model_id(self) -> str:
        return self._inner.model_id

    @property
    def dimensions(self) -> int:
        return self._inner.dimensions

    def embed(self, inputs: Sequence[EmbeddingInput]) -> EmbeddingResult:
        estimate = estimate_tokens("".join(i.text + (i.title or "") for i in inputs))
        return self._meter.run(estimate, lambda: self._inner.embed(inputs), lambda r: r.usage)
