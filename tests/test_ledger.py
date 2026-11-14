from datetime import UTC, datetime
from pathlib import Path

from niyam.models.ledger import CostLedger, quota_day
from niyam.models.types import Usage


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def test_quota_day_uses_pacific_time() -> None:
    # 06:00 UTC on 15 Nov is 22:00 on 14 Nov in Los Angeles (PST, UTC-8).
    assert quota_day(datetime(2026, 11, 15, 6, 0, tzinfo=UTC)).isoformat() == "2026-11-14"
    assert quota_day(datetime(2026, 11, 15, 9, 0, tzinfo=UTC)).isoformat() == "2026-11-15"


def test_counts_requests_per_model_per_quota_day(tmp_path: Path) -> None:
    clock = FakeClock(datetime(2026, 11, 15, 6, 0, tzinfo=UTC))
    ledger = CostLedger(tmp_path / "l.sqlite", clock=clock)
    ledger.record("gemini", "m1", Usage(input_tokens=10), 0.0)
    ledger.record("gemini", "m1", Usage(input_tokens=10), 0.0)
    ledger.record("gemini", "m2", Usage(input_tokens=10), 0.0)
    assert ledger.requests_today("m1") == 2

    clock.now = datetime(2026, 11, 15, 9, 0, tzinfo=UTC)  # past Pacific midnight
    assert ledger.requests_today("m1") == 0
    ledger.close()


def test_spend_is_summed_per_provider_and_summary_aggregates(tmp_path: Path) -> None:
    ledger = CostLedger(tmp_path / "l.sqlite")
    ledger.record("jev", "j", Usage(input_tokens=100), 0.25)
    ledger.record("jev", "j", Usage(input_tokens=50, output_tokens=5), 0.5)
    ledger.record("gemini", "g", Usage(input_tokens=7, thought_tokens=3), 0.0)
    assert ledger.spend_usd("jev") == 0.75
    assert ledger.spend_usd("unknown") == 0.0

    rows = {row.model_id: row for row in ledger.summary()}
    assert rows["j"].requests == 2
    assert rows["j"].input_tokens == 150
    assert rows["g"].thought_tokens == 3
    ledger.close()
