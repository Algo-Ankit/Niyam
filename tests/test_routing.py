"""Greetings and unrelated messages get a fixed reply after extraction (D72)."""

from datetime import date
from typing import Any, cast

import psycopg
import pytest
from pydantic import BaseModel

from fakes import FakeDecisionModel, FakeEmbedder
from niyam.api import reply_json
from niyam.assistant import pipeline
from niyam.models.types import GenerationRequest, GenerationResult, Usage
from niyam.retrieval.store import Hit

AS_OF = date(2026, 11, 21)
CITATION = "8 CFR 214.2(f)(11)(i)(B)(2)"


class KindGenerator:
    """Extracts the given kind and facts; explains only if the pipeline goes that far."""

    model_id = "scripted"

    def __init__(self, kind: str, facts: dict[str, Any]) -> None:
        self._extraction = {"kind": kind, "facts": facts, "question": "What can you do?"}
        self.explained = False

    def generate[T: BaseModel](self, request: GenerationRequest[T]) -> GenerationResult[T]:
        if request.schema is pipeline.Extraction:
            data: dict[str, Any] = self._extraction
        else:
            self.explained = True
            data = {"answerable": True, "explanation": "See the rule.", "citations": [CITATION]}
        return GenerationResult(request.schema.model_validate(data), Usage())


@pytest.fixture
def searched(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    queries: list[str] = []

    def search(conn: object, embedder: object, query: str, k: int) -> list[Hit]:
        queries.append(query)
        return [Hit(CITATION, ("OPT",), "The application window rule.", 0.9)]

    monkeypatch.setattr(pipeline, "search", search)
    monkeypatch.setattr(pipeline, "by_citation", lambda conn, citations: [])
    return queries


def _answer(generator: KindGenerator) -> tuple[pipeline.Reply, list[str]]:
    stages: list[str] = []
    services = pipeline.Services(
        generator, FakeDecisionModel(), FakeEmbedder(), cast(psycopg.Connection, object()), None
    )
    reply = pipeline.answer("hello", AS_OF, services, lambda stage, _ms: stages.append(stage))
    return reply, stages


@pytest.mark.parametrize("kind", ["greeting", "unrelated"])
def test_a_message_without_facts_that_is_not_a_question_gets_the_fixed_reply(
    kind: str, searched: list[str]
) -> None:
    generator = KindGenerator(kind, {})
    reply, stages = _answer(generator)

    assert stages == ["extract"]
    assert searched == [] and not generator.explained
    assert reply.explanation.explanation == pipeline.FIXED_REPLIES[kind]  # type: ignore[index]
    assert reply.explanation.citations == [] and reply.provisions == ()
    assert reply.assessment.findings == () and reply.assessment.missing == ()
    assert reply.rejected_reason is None
    assert reply_json(reply)["kind"] == kind


def test_a_greeting_that_states_a_fact_takes_the_full_pipeline(searched: list[str]) -> None:
    generator = KindGenerator("greeting", {"program_end_date": "2026-05-15"})
    reply, stages = _answer(generator)

    assert stages == list(pipeline.STAGES)
    assert searched and generator.explained
    assert reply.explanation.citations == [CITATION]


def test_the_rendered_greeting_has_no_sources_line(searched: list[str]) -> None:
    reply, _ = _answer(KindGenerator("greeting", {}))
    text = pipeline.render(reply)
    assert pipeline.FIXED_REPLIES["greeting"] in text
    assert "Sources:" not in text


def test_kind_defaults_to_question_for_extractions_without_it() -> None:
    extraction = pipeline.Extraction.model_validate({"facts": {}, "question": "q"})
    assert extraction.kind == "question"
