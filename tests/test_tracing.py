"""Langfuse tracing of `pipeline.answer` (D67), against a fake client: no network."""

import logging
from collections.abc import Mapping
from datetime import date
from typing import Any, cast

import psycopg
import pytest
from langfuse import Langfuse
from pydantic import BaseModel, SecretStr

from fakes import FakeDecisionModel, FakeEmbedder
from niyam.assistant import pipeline, tracing
from niyam.assistant.tracing import NO_TRACING, LangfuseTracer, build_tracer
from niyam.config import Settings
from niyam.models.errors import ModelError, ProviderUnavailableError
from niyam.models.types import DecisionResult, GenerationRequest, GenerationResult, Usage
from niyam.retrieval.store import Hit

AS_OF = date(2026, 11, 20)
MESSAGE = "My SEVIS ID is N0012345678. My program ended 2026-05-15; when does my OPT window close?"
QUESTION = "When does the OPT application window close?"
CITATION = "8 CFR 214.2(f)(11)(i)(B)(2)"


class FakeObservation:
    def __init__(self, name: str) -> None:
        self.name = name
        self.children: list[FakeObservation] = []
        self.updates: list[dict[str, Any]] = []
        self.scores: dict[str, tuple[float, str]] = {}
        self.ended = False

    def start_observation(self, *, name: str) -> "FakeObservation":
        child = FakeObservation(name)
        self.children.append(child)
        return child

    def update(self, **fields: Any) -> None:
        self.updates.append(fields)

    def score_trace(self, *, name: str, value: float, data_type: str) -> None:
        self.scores[name] = (value, data_type)

    def end(self) -> None:
        self.ended = True


class FakeLangfuse:
    def __init__(self, fail: bool = False) -> None:
        self.roots: list[FakeObservation] = []
        self.calls = 0
        self._fail = fail

    def start_observation(self, *, name: str, as_type: str) -> FakeObservation:
        self.calls += 1
        if self._fail:
            raise ConnectionError("langfuse is down")
        root = FakeObservation(name)
        self.roots.append(root)
        return root


class ScriptedGenerator:
    """Returns the extraction, then the explanation, by the schema the pipeline asks for."""

    model_id = "scripted"

    def __init__(self, citations: list[str], fail: bool = False) -> None:
        self._citations = citations
        self._fail = fail

    def generate[T: BaseModel](self, request: GenerationRequest[T]) -> GenerationResult[T]:
        if self._fail:
            raise ProviderUnavailableError("generator down")
        if request.schema is pipeline.Extraction:
            data: dict[str, Any] = {
                "facts": {"program_end_date": "2026-05-15"},
                "question": QUESTION,
            }
        else:
            data = {
                "answerable": True,
                "explanation": "See the rule.",
                "citations": self._citations,
            }
        return GenerationResult(request.schema.model_validate(data), Usage())


class FailingDecider:
    model_id = "failing"

    def decide(self, state: str, questions: Mapping[str, str]) -> DecisionResult:
        raise ModelError("reranker down")


@pytest.fixture(autouse=True)
def _no_database(monkeypatch: pytest.MonkeyPatch) -> None:
    hit = Hit(CITATION, ("OPT",), "The application window rule.", 0.9)
    monkeypatch.setattr(pipeline, "search", lambda conn, embedder, query, k: [hit])
    monkeypatch.setattr(pipeline, "by_citation", lambda conn, citations: [])


def _services(
    tracer: tracing.Tracer,
    generator: ScriptedGenerator | None = None,
    decider: FakeDecisionModel | FailingDecider | None = None,
) -> pipeline.Services:
    return pipeline.Services(
        generator or ScriptedGenerator([CITATION]),
        decider or FakeDecisionModel(),
        FakeEmbedder(),
        cast(psycopg.Connection, object()),
        None,
        tracer,
    )


def test_one_trace_per_answer_with_a_span_per_stage_and_scores() -> None:
    client = FakeLangfuse()
    reply = pipeline.answer(MESSAGE, AS_OF, _services(LangfuseTracer(cast(Langfuse, client))))

    (root,) = client.roots
    assert root.name == "answer" and root.ended
    assert [c.name for c in root.children] == list(pipeline.STAGES)
    assert all(c.ended and not c.updates for c in root.children)
    assert root.scores == {
        "withheld": (0, "BOOLEAN"),
        "rerank_failed": (0, "BOOLEAN"),
        "findings": (len(reply.assessment.findings), "NUMERIC"),
    }
    assert reply.rejected_reason is None and reply.assessment.findings


def test_only_the_restated_question_is_sent_never_the_message() -> None:
    client = FakeLangfuse()
    pipeline.answer(MESSAGE, AS_OF, _services(LangfuseTracer(cast(Langfuse, client))))

    sent = repr(client.roots[0].updates)
    assert QUESTION in sent and "N0012345678" not in sent and MESSAGE not in sent


def test_withheld_explanation_and_failed_rerank_are_scored() -> None:
    client = FakeLangfuse()
    services = _services(
        LangfuseTracer(cast(Langfuse, client)),
        generator=ScriptedGenerator(["8 CFR 214.2(f)(99)"]),
        decider=FailingDecider(),
    )
    reply = pipeline.answer(MESSAGE, AS_OF, services)

    assert reply.rejected_reason is not None and reply.rerank_error is not None
    scores = client.roots[0].scores
    assert scores["withheld"] == (1, "BOOLEAN")
    assert scores["rerank_failed"] == (1, "BOOLEAN")


def test_a_failing_stage_is_marked_with_its_error_type_and_still_raises() -> None:
    client = FakeLangfuse()
    services = _services(
        LangfuseTracer(cast(Langfuse, client)), generator=ScriptedGenerator([], fail=True)
    )
    with pytest.raises(ProviderUnavailableError):
        pipeline.answer(MESSAGE, AS_OF, services)

    (root,) = client.roots
    (extract,) = root.children
    error = {"level": "ERROR", "status_message": "ProviderUnavailableError"}
    assert extract.updates == [error] and extract.ended
    assert root.updates == [error] and root.ended and not root.scores


def test_langfuse_failure_never_breaks_answers_and_is_logged_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = FakeLangfuse(fail=True)
    services = _services(LangfuseTracer(cast(Langfuse, client)))
    with caplog.at_level(logging.WARNING, logger="niyam.assistant.tracing"):
        first = pipeline.answer(MESSAGE, AS_OF, services)
        second = pipeline.answer(MESSAGE, AS_OF, services)

    assert first.rejected_reason is None and second.rejected_reason is None
    assert client.calls == 1
    assert [r.getMessage() for r in caplog.records] == [
        "Langfuse tracing failed (ConnectionError); off until restart"
    ]


def test_answers_are_untraced_by_default() -> None:
    services = pipeline.Services(
        ScriptedGenerator([CITATION]),
        FakeDecisionModel(),
        FakeEmbedder(),
        cast(psycopg.Connection, object()),
        None,
    )
    assert services.tracer is NO_TRACING
    assert pipeline.answer(MESSAGE, AS_OF, services).rejected_reason is None


def _settings(tracing_on: bool) -> Settings:
    return Settings.model_construct(
        langfuse_public_key=SecretStr("pk-lf-test"),
        langfuse_secret_key=SecretStr("sk-lf-test"),
        langfuse_host="http://127.0.0.1:9",
        langfuse_tracing=tracing_on,
    )


def test_build_tracer_is_off_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected(**_: Any) -> None:
        raise AssertionError("must not contact Langfuse")

    monkeypatch.setattr(tracing, "Langfuse", unexpected)
    assert build_tracer(_settings(tracing_on=False)) is NO_TRACING


def test_build_tracer_falls_back_when_langfuse_is_unreachable(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    class Unreachable:
        def __init__(self, **_: Any) -> None:
            pass

        def auth_check(self) -> bool:
            raise ConnectionError("no route")

    monkeypatch.setattr(tracing, "Langfuse", Unreachable)
    with caplog.at_level(logging.WARNING, logger="niyam.assistant.tracing"):
        assert build_tracer(_settings(tracing_on=True)) is NO_TRACING
    assert [r.getMessage() for r in caplog.records] == [
        "Langfuse unavailable (ConnectionError); answers will not be traced"
    ]


def test_build_tracer_falls_back_when_credentials_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Rejecting:
        shut_down = False

        def __init__(self, **_: Any) -> None:
            pass

        def auth_check(self) -> bool:
            return False

        def shutdown(self) -> None:
            Rejecting.shut_down = True

    monkeypatch.setattr(tracing, "Langfuse", Rejecting)
    assert build_tracer(_settings(tracing_on=True)) is NO_TRACING
    assert Rejecting.shut_down
