import json
import threading
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from niyam.api import BUSY, INTERNAL, Answerer, AskLimiter, build_app
from niyam.assistant import pipeline
from niyam.corpus.download import ECFR_TITLE_8, last_modified_date
from niyam.models.errors import QuotaExhaustedError
from niyam.retrieval.store import Hit
from niyam.rules.opt import StudentFacts, assess

AS_OF = date(2026, 11, 20)
ORIGIN = "http://localhost:5173"


def _reply(rejected_reason: str | None = None, trace_id: str | None = None) -> pipeline.Reply:
    facts = StudentFacts(program_end_date=date(2026, 5, 15))
    return pipeline.Reply(
        extraction=pipeline.Extraction(facts=facts, question="When must I file for OPT?"),
        assessment=assess(facts, AS_OF),
        provisions=(Hit("214.2(f)(11)(i)(B)(2)", ("OPT",), "Filing window text.", 0.9),),
        explanation=pipeline.Explanation(
            answerable=True, explanation="File within the window.", citations=["214.2(f)(11)"]
        ),
        rejected_reason=rejected_reason,
        rerank_error=None,
        trace_id=trace_id,
    )


def _answering(reply: pipeline.Reply) -> Answerer:
    def answer(message: str, as_of: date, on_stage: pipeline.StageCallback) -> pipeline.Reply:
        for stage in pipeline.STAGES:
            on_stage(stage, 7)
        return reply

    return answer


def _raising(error: Exception) -> Answerer:
    def answer(message: str, as_of: date, on_stage: pipeline.StageCallback) -> pipeline.Reply:
        on_stage("extract", 3)
        raise error

    return answer


def _client(answerer: Answerer, limiter: AskLimiter | None = None) -> TestClient:
    return TestClient(build_app(answerer, limiter or AskLimiter(100, 100), [ORIGIN]))


def _events(body: str) -> list[tuple[str, dict[str, Any]]]:
    events = []
    for block in body.strip().split("\n\n"):
        name_line, data_line = block.split("\n")
        events.append((name_line.removeprefix("event: "), json.loads(data_line[len("data: ") :])))
    return events


def _ask(
    client: TestClient, message: str = "When must I file for OPT?"
) -> list[tuple[str, dict[str, Any]]]:
    response = client.post("/api/ask", json={"message": message, "as_of": AS_OF.isoformat()})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    return _events(response.text)


def test_every_stage_streams_in_order_then_the_reply() -> None:
    events = _ask(_client(_answering(_reply())))
    assert [name for name, _ in events] == ["stage"] * len(pipeline.STAGES) + ["reply"]
    assert [data["stage"] for _, data in events[:-1]] == list(pipeline.STAGES)
    reply = events[-1][1]
    assert reply["explanation"] == "File within the window."
    assert reply["withheld_reason"] is None
    assert reply["disclaimer"] == pipeline.DISCLAIMER
    assert reply["facts"]["program_end_date"] == "2026-05-15"


def test_a_rejected_explanation_is_withheld_with_its_reason() -> None:
    reply = _ask(_client(_answering(_reply("stated dates the rules engine did not compute"))))[-1]
    assert reply[1]["explanation"] is None
    assert reply[1]["citations"] == []
    assert reply[1]["withheld_reason"] == "stated dates the rules engine did not compute"


def test_quota_errors_reach_the_browser_as_busy_without_details() -> None:
    events = _ask(_client(_raising(QuotaExhaustedError("gemini RPD 500 reached, key=abc"))))
    assert events[-1] == ("error", {"code": "busy", "message": BUSY})


def test_unexpected_errors_are_generic_and_never_leak_their_text() -> None:
    events = _ask(_client(_raising(RuntimeError("postgres://user:secret@host"))))
    assert events[-1] == ("error", {"code": "internal", "message": INTERNAL})
    assert "secret" not in json.dumps(events)


def test_a_message_that_is_too_short_or_too_long_is_rejected() -> None:
    client = _client(_answering(_reply()))
    assert client.post("/api/ask", json={"message": "hi"}).status_code == 422
    assert client.post("/api/ask", json={"message": "x" * 2001}).status_code == 422


def test_a_client_over_its_hourly_limit_gets_429_with_retry_after() -> None:
    client = _client(_answering(_reply()), AskLimiter(per_client_per_hour=1, daily_cap=100))
    _ask(client)
    response = client.post("/api/ask", json={"message": "When must I file for OPT?"})
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0


def test_cors_allows_only_the_configured_origin() -> None:
    client = _client(_answering(_reply()))
    preflight = {"Access-Control-Request-Method": "POST"}
    allowed = client.options("/api/ask", headers={"Origin": ORIGIN, **preflight})
    other = client.options("/api/ask", headers={"Origin": "https://evil.example", **preflight})
    assert allowed.headers["access-control-allow-origin"] == ORIGIN
    assert "access-control-allow-origin" not in other.headers


class _Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> _Clock:
    return _Clock(datetime(2026, 11, 20, 18, 0, tzinfo=UTC))  # 10:00 Pacific


def test_hourly_limit_frees_up_after_an_hour(clock: _Clock) -> None:
    limiter = AskLimiter(per_client_per_hour=2, daily_cap=100, clock=clock)
    assert limiter.admit("a") is None
    assert limiter.admit("a") is None
    refusal = limiter.admit("a")
    assert refusal is not None
    assert refusal.retry_after_seconds == 3601
    assert limiter.admit("b") is None  # other clients are unaffected
    clock.now += timedelta(hours=1)
    assert limiter.admit("a") is None


def test_daily_cap_spans_clients_and_resets_at_pacific_midnight(clock: _Clock) -> None:
    limiter = AskLimiter(per_client_per_hour=10, daily_cap=2, clock=clock)
    assert limiter.admit("a") is None
    assert limiter.admit("b") is None
    refusal = limiter.admit("c")
    assert refusal is not None
    assert refusal.retry_after_seconds == 14 * 3600 + 1  # 10:00 to midnight Pacific
    clock.now += timedelta(hours=14)
    assert limiter.admit("c") is None


def test_health_reports_the_corpus_snapshot_date() -> None:
    app = build_app(_answering(_reply()), AskLimiter(1, 1), [ORIGIN], corpus_snapshot=AS_OF)
    assert TestClient(app).get("/api/health").json() == {
        "status": "ok",
        "corpus_snapshot": "2026-11-20",
    }


def test_snapshot_date_comes_from_the_manifest_last_modified_header(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    entry = {"url": ECFR_TITLE_8, "last_modified": "Thu, 15 Oct 2026 21:57:06 GMT"}
    manifest.write_text(json.dumps([entry]), encoding="utf-8")
    assert last_modified_date(manifest, ECFR_TITLE_8) == date(2026, 10, 15)
    assert last_modified_date(tmp_path / "missing.json", ECFR_TITLE_8) is None


def test_the_limit_keys_on_the_platform_client_ip_header() -> None:
    app = build_app(
        _answering(_reply()),
        AskLimiter(per_client_per_hour=1, daily_cap=100),
        [ORIGIN],
        client_ip_header="x-real-ip",
    )
    client = TestClient(app)
    body = {"message": "When must I file for OPT?"}
    first = client.post("/api/ask", json=body, headers={"x-real-ip": "203.0.113.7"})
    second = client.post("/api/ask", json=body, headers={"x-real-ip": "203.0.113.7"})
    other = client.post("/api/ask", json=body, headers={"x-real-ip": "198.51.100.2"})
    assert (first.status_code, second.status_code, other.status_code) == (200, 429, 200)


def test_after_reply_runs_once_the_reply_is_sent_even_if_it_fails() -> None:
    calls: list[str] = []

    def flaky_flush() -> None:
        calls.append("flush")
        raise ConnectionError("langfuse is down")

    app = build_app(_answering(_reply()), AskLimiter(100, 100), [ORIGIN], after_reply=flaky_flush)
    events = _ask(TestClient(app))
    assert events[-1][0] == "reply"
    assert calls == ["flush"]


def test_an_ask_past_its_deadline_ends_with_busy_instead_of_hanging() -> None:
    release = threading.Event()

    def stuck(message: str, as_of: date, on_stage: pipeline.StageCallback) -> pipeline.Reply:
        on_stage("extract", 3)
        release.wait(5)  # a provider that never answers
        return _reply()

    app = build_app(stuck, AskLimiter(100, 100), [ORIGIN], deadline_seconds=0.2)
    try:
        events = _ask(TestClient(app))
    finally:
        release.set()
    assert [name for name, _ in events] == ["stage", "error"]
    assert events[-1][1] == {"code": "busy", "message": BUSY}


def test_a_reply_sent_in_time_is_not_followed_by_busy_when_cleanup_runs_late() -> None:
    def slow_flush() -> None:
        time.sleep(0.4)

    app = build_app(
        _answering(_reply()),
        AskLimiter(100, 100),
        [ORIGIN],
        deadline_seconds=0.2,
        after_reply=slow_flush,
    )
    events = _ask(TestClient(app))
    assert events[-1][0] == "reply"
    assert all(name != "error" for name, _ in events)


def test_reply_includes_trace_id_and_feedback_endpoint_records_it() -> None:
    calls: list[tuple[str, bool, str | None]] = []

    def record(trace_id: str, helpful: bool, comment: str | None) -> bool:
        calls.append((trace_id, helpful, comment))
        return True

    app = build_app(
        _answering(_reply(trace_id="trace_abc_12345")),
        AskLimiter(100, 100),
        [ORIGIN],
        record_feedback=record,
    )
    client = TestClient(app)
    reply = _ask(client)[-1][1]
    assert reply["trace_id"] == "trace_abc_12345"

    res = client.post(
        "/api/feedback",
        json={"trace_id": "trace_abc_12345", "helpful": False, "comment": "  wrong deadline  "},
    )
    assert res.status_code == 200 and res.json() == {"recorded": True}
    blank = client.post(
        "/api/feedback",
        json={"trace_id": "trace_abc_12345", "helpful": True, "comment": "   "},
    )
    assert blank.status_code == 200
    assert calls == [
        ("trace_abc_12345", False, "wrong deadline"),
        ("trace_abc_12345", True, None),
    ]


def test_feedback_validation_rate_limit_and_error_safety() -> None:
    def broken(trace_id: str, helpful: bool, comment: str | None) -> bool:
        raise RuntimeError("boom")

    app = build_app(
        _answering(_reply()),
        AskLimiter(100, 100),
        [ORIGIN],
        record_feedback=broken,
        feedback_limiter=AskLimiter(1, 10),
    )
    client = TestClient(app)
    assert (
        client.post("/api/feedback", json={"trace_id": "short", "helpful": True}).status_code == 422
    )
    assert (
        client.post("/api/feedback", json={"trace_id": "bad;trace_id", "helpful": True}).status_code
        == 422
    )
    assert (
        client.post(
            "/api/feedback",
            json={"trace_id": "trace_valid_123", "helpful": False, "comment": "x" * 301},
        ).status_code
        == 422
    )

    first = client.post("/api/feedback", json={"trace_id": "trace_valid_123", "helpful": False})
    assert first.status_code == 200 and first.json() == {"recorded": False}
    limited = client.post("/api/feedback", json={"trace_id": "trace_valid_123", "helpful": True})
    assert limited.status_code == 429 and int(limited.headers["retry-after"]) > 0
