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
        self._events: deque[tuple[float, int]] = deque()
        self._lock = threading.Lock()

    def acquire(self, tokens: int) -> None:
        if self._tpm is not None and tokens > self._tpm:
            raise ValueError(
                f"request of {tokens} tokens exceeds the {self._tpm} tokens/minute limit"
            )
        while True:
            with self._lock:
                wait = self._seconds_until_fits(tokens)
                if wait <= 0:
                    self._events.append((self._clock(), tokens))
                    return
            self._sleep(wait)

    def _seconds_until_fits(self, tokens: int) -> float:
        now = self._clock()
        while self._events and now - self._events[0][0] >= WINDOW_SECONDS:
            self._events.popleft()

        waits = [0.0]
        if self._rpm is not None and len(self._events) >= self._rpm:
            oldest_blocking = self._events[len(self._events) - self._rpm]
            waits.append(oldest_blocking[0] + WINDOW_SECONDS - now)
        if self._tpm is not None:
            excess = sum(t for _, t in self._events) + tokens - self._tpm
            for at, used in self._events:
                if excess <= 0:
                    break
                excess -= used
                waits.append(at + WINDOW_SECONDS - now)
        return max(waits)
