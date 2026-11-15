import pytest

from niyam.models.ratelimit import SlidingWindowLimiter, estimate_tokens


class FakeTime:
    """A clock that only moves when the limiter sleeps."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def make(rpm: int | None, tpm: int | None) -> tuple[SlidingWindowLimiter, FakeTime]:
    t = FakeTime()
    return SlidingWindowLimiter(rpm, tpm, clock=t.clock, sleep=t.sleep), t


def test_no_limits_never_waits() -> None:
    limiter, t = make(None, None)
    for _ in range(1000):
        limiter.acquire(10_000)
    assert t.slept == []


def test_requests_per_minute_blocks_until_oldest_expires() -> None:
    limiter, t = make(rpm=2, tpm=None)
    limiter.acquire(1)
    t.now = 10.0
    limiter.acquire(1)
    limiter.acquire(1)  # third request must wait for the first to leave the window
    assert t.now == pytest.approx(60.0)


def test_tokens_per_minute_waits_for_enough_tokens_to_expire() -> None:
    limiter, t = make(rpm=None, tpm=1000)
    limiter.acquire(600)  # at t=0
    t.now = 20.0
    limiter.acquire(300)  # at t=20, total 900
    limiter.acquire(500)  # needs the 600 from t=0 gone: wait until t=60
    assert t.now == pytest.approx(60.0)
    limiter.acquire(200)  # 300 + 500 + 200 = 1000 fits without waiting
    assert t.now == pytest.approx(60.0)


def test_single_request_larger_than_limit_is_rejected() -> None:
    limiter, _ = make(rpm=None, tpm=100)
    with pytest.raises(ValueError, match="exceeds"):
        limiter.acquire(101)


def test_estimate_tokens_is_positive_and_scales() -> None:
    assert estimate_tokens("") == 1
    assert estimate_tokens("a" * 400) == 100


def test_a_batch_counts_as_many_requests() -> None:
    limiter, t = make(rpm=100, tpm=None)
    limiter.acquire(1, requests=90)
    t.now = 5.0
    limiter.acquire(1, requests=90)  # 180 > 100: waits for the first batch to leave the window
    assert t.now == pytest.approx(60.0)


def test_a_batch_larger_than_the_limit_is_refused() -> None:
    limiter, _ = make(rpm=100, tpm=None)
    with pytest.raises(ValueError, match="101 requests"):
        limiter.acquire(1, requests=101)
