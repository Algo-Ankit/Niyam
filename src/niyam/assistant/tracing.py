"""Langfuse tracing for answers (D67): one trace per answer, one span per stage, three scores.

Tracing never changes an answer. Every Langfuse call is guarded; the first failure is logged once
and tracing stays off for the rest of the process. Only the restated question is sent, never the
student's own message, and no secret or error text leaves the process (error type names only).
"""

import logging
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from datetime import date
from functools import partial
from typing import Any, Protocol

from langfuse import Langfuse

from niyam.config import Settings

_log = logging.getLogger(__name__)


class Trace(Protocol):
    def stage(self, name: str) -> AbstractContextManager[None]: ...

    def question(self, text: str, as_of: date) -> None: ...

    def finish(self, *, withheld: bool, rerank_failed: bool, findings: int) -> None: ...


class Tracer(Protocol):
    def trace(self) -> AbstractContextManager[Trace]: ...


class _NoTrace:
    def stage(self, name: str) -> AbstractContextManager[None]:
        return nullcontext()

    def question(self, text: str, as_of: date) -> None:
        return None

    def finish(self, *, withheld: bool, rerank_failed: bool, findings: int) -> None:
        return None


class NoTracing:
    """The default: answers are not traced (tests, evals, or tracing switched off)."""

    def trace(self) -> AbstractContextManager[Trace]:
        return nullcontext(_NoTrace())


NO_TRACING = NoTracing()


class LangfuseTracer:
    """Sends each answer to Langfuse; spans are exported by the SDK's background thread."""

    def __init__(self, client: Langfuse) -> None:
        self._client = client
        self._failed = False

    @contextmanager
    def trace(self) -> Iterator[Trace]:
        root = self.guard(lambda: self._client.start_observation(name="answer", as_type="chain"))
        trace = _LangfuseTrace(self, root)
        try:
            yield trace
        except BaseException as error:
            self.guard(partial(_mark_error, root, error))
            raise
        finally:
            self.guard(lambda: _end(root))

    def guard[T](self, action: Callable[[], T]) -> T | None:
        """`action()`, or None once any Langfuse call has failed."""
        if self._failed:
            return None
        try:
            return action()
        except Exception as error:
            self._failed = True
            _log.warning("Langfuse tracing failed (%s); off until restart", type(error).__name__)
            return None


class _LangfuseTrace:
    def __init__(self, tracer: LangfuseTracer, root: Any) -> None:
        self._tracer = tracer
        self._root = root

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        guard, root = self._tracer.guard, self._root
        span = guard(lambda: root.start_observation(name=name) if root is not None else None)
        try:
            yield
        except BaseException as error:
            guard(partial(_mark_error, span, error))
            raise
        finally:
            guard(lambda: _end(span))

    def question(self, text: str, as_of: date) -> None:
        if self._root is not None:
            payload = {"question": text, "as_of": as_of.isoformat()}
            self._tracer.guard(lambda: self._root.update(input=payload))

    def finish(self, *, withheld: bool, rerank_failed: bool, findings: int) -> None:
        root = self._root
        if root is None:
            return
        outcome = {"withheld": withheld, "rerank_failed": rerank_failed, "findings": findings}

        def send() -> None:
            root.update(output=outcome)
            root.score_trace(name="withheld", value=int(withheld), data_type="BOOLEAN")
            root.score_trace(name="rerank_failed", value=int(rerank_failed), data_type="BOOLEAN")
            root.score_trace(name="findings", value=findings, data_type="NUMERIC")

        self._tracer.guard(send)


def _mark_error(observation: Any, error: BaseException) -> None:
    if observation is not None:
        observation.update(level="ERROR", status_message=type(error).__name__)


def _end(observation: Any) -> None:
    if observation is not None:
        observation.end()


# NOTE: auth_check() raises the transport error when the host is down instead of returning
# False, and flush() blocks for seconds, so we check once at startup and never flush per answer.
def build_tracer(settings: Settings) -> Tracer:
    """A Langfuse tracer if `LANGFUSE_TRACING` is on and the keys work, else `NO_TRACING`."""
    if not settings.langfuse_tracing:
        return NO_TRACING
    try:
        client = Langfuse(
            public_key=settings.langfuse_public_key.get_secret_value(),
            secret_key=settings.langfuse_secret_key.get_secret_value(),
            host=settings.langfuse_host,
        )
        if client.auth_check():
            return LangfuseTracer(client)
        client.shutdown()
        _log.warning("Langfuse rejected the credentials; answers will not be traced")
    except Exception as error:
        _log.warning("Langfuse unavailable (%s); answers will not be traced", type(error).__name__)
    return NO_TRACING
