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
from typing import Any

import psycopg
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from niyam.assistant import pipeline
from niyam.config import Settings, get_settings
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
    return build_app(
        _live_answerer(settings, models),
        AskLimiter(settings.asks_per_ip_per_hour, settings.demo_daily_cap),
        settings.cors_origins,
        on_shutdown=models.close,
    )


def build_app(
    answerer: Answerer,
    limiter: AskLimiter,
    cors_origins: list[str],
    on_shutdown: Callable[[], None] = lambda: None,
) -> FastAPI:
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
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/ask")
    def ask(body: AskRequest, request: Request) -> StreamingResponse:
        client = request.client.host if request.client else "unknown"
        refusal = limiter.admit(client)
        if refusal is not None:
            raise HTTPException(
                status_code=429,
                detail=refusal.message,
                headers={"Retry-After": str(refusal.retry_after_seconds)},
            )
        events = _events(answerer, body.message, body.as_of or date.today())
        return StreamingResponse(
            events,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


def _live_answerer(settings: Settings, models: ModelSuite) -> Answerer:
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
            )
            return pipeline.answer(message, as_of, services, on_stage)

    return answer


def _events(answerer: Answerer, message: str, as_of: date) -> Iterator[str]:
    """Runs the answerer in a thread and yields its stages, then the reply or an error."""
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
            events.put(None)

    threading.Thread(target=work, daemon=True).start()
    while (event := events.get()) is not None:
        yield event


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def reply_json(reply: pipeline.Reply) -> dict[str, Any]:
    """The reply as the web page shows it; the explanation only if it passed the checks."""
    shown = reply.rejected_reason is None
    return {
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
