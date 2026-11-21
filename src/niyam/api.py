"""HTTP API for the web app (D64): `uvicorn niyam.api:create_app --factory --port 8000`.

`POST /api/ask` streams server-sent events: a `stage` event as each pipeline stage finishes,
then one `reply` event, or one `error` event. Asks are limited per client and per quota day,
because the free generator quota is shared with the evals.
"""

import json
import logging
import queue
import threading
from collections import deque
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from time import monotonic
from typing import Any

import psycopg
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from niyam.assistant import pipeline
from niyam.assistant.tracing import Tracer, build_tracer
from niyam.cli import MANIFEST
from niyam.config import Settings, get_settings
from niyam.corpus.download import ECFR_TITLE_8, last_modified_date
from niyam.models.errors import (
    BudgetExceededError,
    ProviderUnavailableError,
    QuotaExhaustedError,
    RateLimitedError,
)
from niyam.models.factory import ModelSuite, build_models
from niyam.models.ledger import QUOTA_TIMEZONE, quota_day

Answerer = Callable[[str, date, pipeline.StageCallback], pipeline.Reply]

HOUR = timedelta(hours=1)
BUSY = "The assistant is at its free daily limit or the model is overloaded. Try again later."
INTERNAL = "Something went wrong while answering. Try again later."
_BUSY_ERRORS = (
    QuotaExhaustedError,
    RateLimitedError,
    ProviderUnavailableError,
    BudgetExceededError,
)
_log = logging.getLogger(__name__)


class AskRequest(BaseModel):
    message: str = Field(min_length=3, max_length=2000)
    as_of: date | None = None  # the student's local date; the server's date if omitted


@dataclass(frozen=True)
class Refusal:
    message: str
    retry_after_seconds: int


class AskLimiter:
    """Admits an ask while its client is under the hourly limit and the quota day is under cap.

    State is in memory: one process, reset on restart (D64).
    """

    def __init__(
        self,
        per_client_per_hour: int,
        daily_cap: int,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._per_client = per_client_per_hour
        self._daily_cap = daily_cap
        self._clock = clock
        self._lock = threading.Lock()
        self._recent: dict[str, deque[datetime]] = {}
        self._day: date | None = None
        self._day_count = 0

    def admit(self, client: str) -> Refusal | None:
        with self._lock:
            now = self._clock()
            day = quota_day(now)
            if day != self._day:
                self._day, self._day_count = day, 0
                self._recent = {c: t for c, t in self._recent.items() if now - t[-1] < HOUR}
            if self._day_count >= self._daily_cap:
                return Refusal("Today's free limit for the demo is used up.", _until_next(day, now))
            recent = self._recent.setdefault(client, deque())
            while recent and now - recent[0] >= HOUR:
                recent.popleft()
            if len(recent) >= self._per_client:
                wait = (recent[0] + HOUR - now).total_seconds()
                return Refusal("Too many questions this hour.", max(1, int(wait) + 1))
            recent.append(now)
            self._day_count += 1
            return None


def _until_next(day: date, now: datetime) -> int:
    """Seconds from `now` until the next quota day starts (midnight Pacific)."""
    midnight = datetime.combine(day + timedelta(days=1), time(), tzinfo=QUOTA_TIMEZONE)
    return max(1, int((midnight - now).total_seconds()) + 1)


def create_app() -> FastAPI:
    """The live app: real models, Postgres and limits from settings."""
    settings = get_settings()
    models = build_models(settings)
    tracer = build_tracer(settings)
    return build_app(
        _live_answerer(settings, models, tracer),
        AskLimiter(settings.asks_per_ip_per_hour, settings.demo_daily_cap),
        settings.cors_origins,
        corpus_snapshot=last_modified_date(MANIFEST, ECFR_TITLE_8),
        client_ip_header=settings.client_ip_header,
        deadline_seconds=settings.ask_deadline_seconds,
        after_reply=tracer.flush,
        on_shutdown=models.close,
    )


def build_app(  # noqa: PLR0913  # each argument is a separate deployment concern
    answerer: Answerer,
    limiter: AskLimiter,
    cors_origins: list[str],
    *,
    corpus_snapshot: date | None = None,
    client_ip_header: str | None = None,
    deadline_seconds: float = 50.0,
    after_reply: Callable[[], None] = lambda: None,
    on_shutdown: Callable[[], None] = lambda: None,
) -> FastAPI:
    """The app. `after_reply` runs once the reply or error is sent, before the stream closes."""

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        on_shutdown()

    app = FastAPI(title="Niyam API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str | None]:
        snapshot = corpus_snapshot.isoformat() if corpus_snapshot else None
        return {"status": "ok", "corpus_snapshot": snapshot}

    @app.post("/api/ask")
    def ask(body: AskRequest, request: Request) -> StreamingResponse:
        refusal = limiter.admit(_client_ip(request, client_ip_header))
        if refusal is not None:
            raise HTTPException(
                status_code=429,
                detail=refusal.message,
                headers={"Retry-After": str(refusal.retry_after_seconds)},
            )
        events = _events(
            answerer, body.message, body.as_of or date.today(), after_reply, deadline_seconds
        )
        return StreamingResponse(
            events,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


def _live_answerer(settings: Settings, models: ModelSuite, tracer: Tracer) -> Answerer:
    def answer(message: str, as_of: date, on_stage: pipeline.StageCallback) -> pipeline.Reply:
        # A connection per ask, closed before the stream ends: Neon drops idle ones (D63).
        with psycopg.connect(
            settings.database_url.get_secret_value(), connect_timeout=20, autocommit=True
        ) as conn:
            services = pipeline.Services(
                models.generator,
                models.decision,
                models.embedder,
                conn,
                settings.generation_thinking_level,
                tracer,
            )
            return pipeline.answer(message, as_of, services, on_stage)

    return answer


# NOTE: `client_ip_header` must name a header the platform overwrites (Vercel sets `x-real-ip`
# to the real client address); a header a client can set would let it dodge the per-IP limit.
def _client_ip(request: Request, client_ip_header: str | None) -> str:
    if client_ip_header:
        value = request.headers.get(client_ip_header, "").split(",")[0].strip()
        if value:
            return value
    return request.client.host if request.client else "unknown"


def _events(
    answerer: Answerer,
    message: str,
    as_of: date,
    after_reply: Callable[[], None],
    deadline_seconds: float,
) -> Iterator[str]:
    """Runs the answerer in a thread and yields its stages, then the reply or an error.

    If no reply or error arrives within `deadline_seconds`, the stream ends with a "busy" error.
    """
    events: queue.Queue[str | None] = queue.Queue()

    def on_stage(stage: pipeline.Stage, ms: int) -> None:
        events.put(_sse("stage", {"stage": stage, "ms": ms}))

    def work() -> None:
        try:
            events.put(_sse("reply", reply_json(answerer(message, as_of, on_stage))))
        except _BUSY_ERRORS as error:
            _log.warning("ask refused by the model layer: %s", type(error).__name__)
            events.put(_sse("error", {"code": "busy", "message": BUSY}))
        except Exception:
            _log.exception("ask failed")
            events.put(_sse("error", {"code": "internal", "message": INTERNAL}))
        finally:
            try:
                after_reply()
            except Exception:
                _log.exception("after-reply hook failed")
            events.put(None)

    threading.Thread(target=work, daemon=True).start()
    deadline = monotonic() + deadline_seconds
    answered = False
    while True:
        try:
            event = events.get(timeout=max(0.0, deadline - monotonic()))
        except queue.Empty:
            # The host kills the request at its own limit with no message; end it first, politely.
            if not answered:
                _log.warning("ask exceeded its %.0f s deadline", deadline_seconds)
                yield _sse("error", {"code": "busy", "message": BUSY})
            return
        if event is None:
            return
        answered = answered or event.startswith(("event: reply", "event: error"))
        yield event


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def reply_json(reply: pipeline.Reply) -> dict[str, Any]:
    """The reply as the web page shows it; the explanation only if it passed the checks."""
    shown = reply.rejected_reason is None
    return {
        "kind": reply.extraction.kind,
        "question": reply.extraction.question,
        "facts": reply.extraction.facts.model_dump(mode="json"),
        "out_of_scope": list(reply.extraction.out_of_scope),
        "findings": [
            {
                "rule": f.rule,
                "citation": f.citation,
                "summary": f.summary,
                "status": f.status,
                "opens": f.opens and f.opens.isoformat(),
                "closes": f.closes and f.closes.isoformat(),
                "assumptions": list(f.assumptions),
            }
            for f in reply.assessment.findings
        ],
        "missing": list(reply.assessment.missing),
        "provisions": [
            {"citation": p.citation, "headings": list(p.headings), "body": p.body}
            for p in reply.provisions
        ],
        "explanation": reply.explanation.explanation if shown else None,
        "citations": reply.explanation.citations if shown else [],
        "withheld_reason": reply.rejected_reason,
        "rerank_failed": reply.rerank_error is not None,
        "disclaimer": pipeline.DISCLAIMER,
        "not_covered": pipeline.NOT_COVERED,
    }
