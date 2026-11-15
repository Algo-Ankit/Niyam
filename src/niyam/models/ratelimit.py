"""Client-side rate limiting so we stay under a model's per-minute quotas instead of hitting 429s.

A sliding 60-second window tracks request count and token volume. `acquire` blocks until
one more request of the given size fits under both limits.
"""

import math
import threading
import time
from collections import deque
from collections.abc import Callable

WINDOW_SECONDS = 60.0


def estimate_tokens(text: str) -> int:
    """Rough pre-call token estimate (about four characters per token).

    Only used to pace requests; the ledger records the provider's actual counts.
    """
    return max(1, math.ceil(len(text) / 4))


class SlidingWindowLimiter:
    def __init__(
        self,
        requests_per_minute: int | None,
        tokens_per_minute: int | None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._rpm = requests_per_minute
        self._tpm = tokens_per_minute
        self._clock = clock
        self._sleep = sleep
        self._events: deque[tuple[float, int, int]] = deque()  # (time, tokens, requests)
        self._lock = threading.Lock()

    def acquire(self, tokens: int, requests: int = 1) -> None:
        """Block until a call of `tokens` that the provider counts as `requests` fits."""
        if self._tpm is not None and tokens > self._tpm:
            raise ValueError(
                f"request of {tokens} tokens exceeds the {self._tpm} tokens/minute limit"
            )
        if self._rpm is not None and requests > self._rpm:
            raise ValueError(f"{requests} requests exceed the {self._rpm} requests/minute limit")
        while True:
            with self._lock:
                wait = self._seconds_until_fits(tokens, requests)
                if wait <= 0:
                    self._events.append((self._clock(), tokens, requests))
                    return
            self._sleep(wait)

    def _seconds_until_fits(self, tokens: int, requests: int) -> float:
        now = self._clock()
        while self._events and now - self._events[0][0] >= WINDOW_SECONDS:
            self._events.popleft()

        waits = [0.0]
        if self._rpm is not None:
            excess = sum(e[2] for e in self._events) + requests - self._rpm
            waits.append(self._wait_for(now, excess, lambda e: e[2]))
        if self._tpm is not None:
            excess = sum(e[1] for e in self._events) + tokens - self._tpm
            waits.append(self._wait_for(now, excess, lambda e: e[1]))
        return max(waits)

    def _wait_for(
        self, now: float, excess: int, amount: Callable[[tuple[float, int, int]], int]
    ) -> float:
        """Seconds until enough of the oldest events leave the window to clear `excess`."""
        wait = 0.0
        for event in self._events:
            if excess <= 0:
                break
            excess -= amount(event)
            wait = event[0] + WINDOW_SECONDS - now
        return wait
