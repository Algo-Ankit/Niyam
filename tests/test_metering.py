import threading
from pathlib import Path

import pytest

from fakes import FakeDecisionModel, FakeEmbedder
from niyam.config import RateLimits
from niyam.models.errors import (
    BudgetExceededError,
    ProviderResponseError,
    ProviderUnavailableError,
    QuotaExhaustedError,
    RateLimitedError,
)
from niyam.models.ledger import CostLedger
from niyam.models.metering import Meter, MeteredDecisionModel, MeteredEmbedder
from niyam.models.types import EmbeddingInput, Usage


@pytest.fixture
def ledger(tmp_path: Path) -> CostLedger:
    return CostLedger(tmp_path / "ledger.sqlite")


def make_meter(ledger: CostLedger, **kwargs: object) -> tuple[Meter, list[float]]:
    slept: list[float] = []
    limits = kwargs.pop("limits", RateLimits())
    meter = Meter("p", "m", limits, ledger, sleep=slept.append, **kwargs)  # type: ignore[arg-type]
    return meter, slept


def test_successful_call_is_recorded_with_cost(ledger: CostLedger) -> None:
    meter, _ = make_meter(ledger, budget_usd=1.0, usd_per_million_input_tokens=1_000_000.0)
    model = MeteredDecisionModel(FakeDecisionModel(), meter)
    result = model.decide("abc", {"q": "?"})
    assert result.probabilities == {"q": 0.9}
    row = ledger.summary()[0]
    assert (row.requests, row.input_tokens, row.cost_usd) == (1, 3, 3.0)


def test_daily_quota_blocks_before_calling(ledger: CostLedger) -> None:
    meter, _ = make_meter(ledger, limits=RateLimits(requests_per_day=1))
    fake = FakeDecisionModel()
    model = MeteredDecisionModel(fake, meter)
    model.decide("s", {"q": "?"})
    with pytest.raises(QuotaExhaustedError):
        model.decide("s", {"q": "?"})
    assert fake.calls == 1


def test_budget_blocks_when_spend_would_exceed_cap(ledger: CostLedger) -> None:
    ledger.record("p", "m", Usage(input_tokens=1), 0.99)
    meter, _ = make_meter(ledger, budget_usd=1.0, usd_per_million_input_tokens=1_000_000.0)
    fake = FakeDecisionModel()
    with pytest.raises(BudgetExceededError):
        MeteredDecisionModel(fake, meter).decide("a long state", {"q": "?"})
    assert fake.calls == 0


def test_rate_limited_call_is_retried_with_backoff_then_succeeds(ledger: CostLedger) -> None:
    attempts = {"n": 0}

    def flaky() -> str:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RateLimitedError("429")
        return "ok"

    meter, slept = make_meter(ledger, max_retries=2)
    assert meter.run(1, flaky, lambda _: Usage(input_tokens=1)) == "ok"
    assert slept == [2.0, 4.0]
    assert ledger.requests_today("m") == 3  # rejected requests still count toward the day


def test_unavailable_provider_is_retried_and_every_attempt_counts(ledger: CostLedger) -> None:
    attempts = {"n": 0}

    def overloaded_twice() -> str:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ProviderUnavailableError("503")
        return "ok"

    meter, slept = make_meter(ledger, max_retries=3)
    assert meter.run(1, overloaded_twice, lambda _: Usage(input_tokens=1)) == "ok"
    assert slept == [2.0, 4.0]
    assert ledger.requests_today("m") == 3


def test_unavailable_provider_gives_up_after_the_last_retry(ledger: CostLedger) -> None:
    def overloaded() -> str:
        raise ProviderUnavailableError("503")

    meter, slept = make_meter(ledger, max_retries=3)
    with pytest.raises(ProviderUnavailableError):
        meter.run(1, overloaded, lambda _: Usage())
    assert slept == [2.0, 4.0, 8.0]
    assert ledger.requests_today("m") == 4


def test_unusable_output_counts_as_a_request_and_is_not_retried_here(ledger: CostLedger) -> None:
    def malformed() -> str:
        raise ProviderResponseError("bad json")

    meter, slept = make_meter(ledger, max_retries=3)
    with pytest.raises(ProviderResponseError):
        meter.run(1, malformed, lambda _: Usage())
    assert (slept, ledger.requests_today("m")) == ([], 1)


def test_retry_after_from_provider_is_honoured(ledger: CostLedger) -> None:
    def limited() -> str:
        raise RateLimitedError("429", retry_after_seconds=7.0)

    meter, slept = make_meter(ledger, max_retries=1)
    with pytest.raises(RateLimitedError):
        meter.run(1, limited, lambda _: Usage())
    assert slept == [7.0]


def test_no_retries_by_default_stops_on_first_429(ledger: CostLedger) -> None:
    def limited() -> str:
        raise RateLimitedError("429")

    meter, slept = make_meter(ledger)
    with pytest.raises(RateLimitedError):
        meter.run(1, limited, lambda _: Usage())
    assert slept == []


def test_concurrent_calls_cannot_overshoot_the_daily_quota(ledger: CostLedger) -> None:
    meter, _ = make_meter(ledger, limits=RateLimits(requests_per_day=1))
    started, release = threading.Event(), threading.Event()

    def slow() -> str:
        started.set()
        release.wait(timeout=5)
        return "ok"

    first = threading.Thread(target=lambda: meter.run(1, slow, lambda _: Usage()))
    first.start()
    assert started.wait(timeout=5)
    with pytest.raises(QuotaExhaustedError):
        meter.run(1, lambda: "never", lambda _: Usage())
    release.set()
    first.join()
    assert ledger.requests_today("m") == 1


def test_embedding_batch_counts_one_request_per_text(ledger: CostLedger) -> None:
    meter, _ = make_meter(ledger, limits=RateLimits(requests_per_day=5))
    embedder = MeteredEmbedder(FakeEmbedder(), meter)
    embedder.embed([EmbeddingInput(t, "document") for t in ("a", "b", "c")])
    assert ledger.requests_today("m") == 3
    with pytest.raises(QuotaExhaustedError):
        embedder.embed([EmbeddingInput(t, "document") for t in ("d", "e", "f")])  # 6 > 5
