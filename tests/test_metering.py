from pathlib import Path

import pytest

from fakes import FakeDecisionModel
from niyam.config import RateLimits
from niyam.models.errors import BudgetExceededError, QuotaExhaustedError, RateLimitedError
from niyam.models.ledger import CostLedger
from niyam.models.metering import Meter, MeteredDecisionModel
from niyam.models.types import Usage


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
