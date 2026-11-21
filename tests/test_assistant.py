from datetime import date
from pathlib import Path
from typing import Any, cast

import psycopg
import pytest
from pydantic import BaseModel

from fakes import FakeDecisionModel, FakeEmbedder
from niyam.assistant import pipeline
from niyam.assistant.pipeline import (
    FIXED_REPLIES,
    MAX_HISTORY_TURNS,
    Explanation,
    Extraction,
    Services,
    Turn,
    _extraction_prompt,
    answer,
    check_explanation,
    fact_dates,
    format_provisions,
    load_learned_corrections,
    match_learned_corrections,
    repair_explanation,
)
from niyam.models.types import GenerationRequest, GenerationResult, Usage
from niyam.retrieval.store import Hit
from niyam.rules.opt import StudentFacts, assess

_ASSESSMENT = assess(StudentFacts(program_end_date=date(2026, 5, 15)), date(2026, 5, 1))
_PROVISIONS = (Hit("8 CFR 214.2(f)(11)(i)(B)(2)", ("OPT",), "up to 90 days prior...", 0.0),)


def _explanation(text: str, citations: list[str]) -> Explanation:
    return Explanation(answerable=True, explanation=text, citations=citations)


def test_grounded_explanation_passes() -> None:
    text = "You can file from 2026-02-14 until 2026-06-14."
    assert (
        check_explanation(
            _explanation(text, ["8 CFR 214.2(f)(11)(i)(B)(2)"]), _ASSESSMENT, _PROVISIONS
        )
        is None
    )


def test_citation_not_given_to_the_model_is_rejected() -> None:
    reason = check_explanation(_explanation("ok", ["8 CFR 214.2(f)(12)"]), _ASSESSMENT, _PROVISIONS)
    assert reason is not None and "8 CFR 214.2(f)(12)" in reason


def test_date_the_rules_engine_did_not_compute_is_rejected() -> None:
    explanation = _explanation("File by 2026-07-14.", ["8 CFR 214.2(f)(11)(i)(B)(2)"])
    reason = check_explanation(explanation, _ASSESSMENT, _PROVISIONS)
    assert reason is not None and "2026-07-14" in reason


def test_dates_written_in_words_are_rejected_because_they_cannot_be_checked() -> None:
    for text in ("File by June 14.", "File by 6/14/2026."):
        reason = check_explanation(
            _explanation(text, ["8 CFR 214.2(f)(11)(i)(B)(2)"]), _ASSESSMENT, _PROVISIONS
        )
        assert reason is not None and "cannot be checked" in reason


def test_dates_the_student_gave_may_be_repeated() -> None:
    explanation = _explanation("Your program ended 2026-05-15.", ["8 CFR 214.2(f)(11)(i)(B)(2)"])
    given = fact_dates(StudentFacts(program_end_date=date(2026, 5, 15)))
    assert check_explanation(explanation, _ASSESSMENT, _PROVISIONS, given) is None
    assert check_explanation(explanation, _ASSESSMENT, _PROVISIONS) is not None


def test_literal_dates_from_retrieved_provisions_are_allowed_but_altered_years_rejected() -> None:
    provisions = (
        Hit(
            "8 CFR 214.2(f)(5)(ii)(C)",
            (),
            "Applies to students admitted on or after September 15, 2026, extended until April 1.",
            0.0,
        ),
    )
    cite = ["8 CFR 214.2(f)(5)(ii)(C)"]
    for ok_text in (
        "This applies starting September 15, 2026 and runs until April 1.",
        "This applies starting 2026-09-15. After day 10 may come another step.",
        "You get a separate 30-day departure period and a decision 15 days later.",
    ):
        assert check_explanation(_explanation(ok_text, cite), _ASSESSMENT, provisions) is None
    for bad_text in (
        "This applies starting September 15, 2027.",
        "This runs until April 1, 2029.",
        "This runs until April 1 2029.",
        "This runs until April 1st, 2029.",
        "File by june 14, 2027.",
        "File by 15 September 2027.",
        "This applies starting 2027-09-15.",
    ):
        assert check_explanation(_explanation(bad_text, cite), _ASSESSMENT, provisions) is not None


def test_repair_explanation_strips_citation_brackets_and_normalizes_known_word_dates() -> None:
    draft = _explanation(
        "Your program ended May 15, 2026. File from Feb 14, 2026 to 14 June 2026.",
        ["[8 CFR 214.2(f)(11)(i)(B)(2)]", " 8 CFR 214.2(f)(11)(i)(B)(2) "],
    )
    given = fact_dates(StudentFacts(program_end_date=date(2026, 5, 15)))
    repaired = repair_explanation(draft, _ASSESSMENT, _PROVISIONS, given)
    assert repaired.citations == ["8 CFR 214.2(f)(11)(i)(B)(2)"]
    assert (
        repaired.explanation == "Your program ended 2026-05-15. File from 2026-02-14 to 2026-06-14."
    )
    assert check_explanation(repaired, _ASSESSMENT, _PROVISIONS, given) is None

    unknown_date = _explanation("File by June 14, 2029.", ["[8 CFR 214.2(f)(11)(i)(B)(2)]"])
    repaired_bad = repair_explanation(unknown_date, _ASSESSMENT, _PROVISIONS, given)
    assert "2029-06-14" not in repaired_bad.explanation
    assert check_explanation(repaired_bad, _ASSESSMENT, _PROVISIONS, given) is not None


class _SelfCorrectingGenerator:
    model_id = "self-correct"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate[T: BaseModel](self, request: GenerationRequest[T]) -> GenerationResult[T]:
        self.prompts.append(request.prompt)
        if request.schema is Extraction:
            data: dict[str, Any] = {
                "facts": {"program_end_date": "2026-05-15"},
                "question": "When must I file for OPT?",
            }
        elif "IMPORTANT CORRECTION:" not in request.prompt:
            data = {
                "answerable": True,
                "explanation": "File by 2026-06-14.",
                "citations": ["8 CFR 214.2(f)(99)"],
            }
        else:
            data = {
                "answerable": True,
                "explanation": "File by 2026-06-14.",
                "citations": ["8 CFR 214.2(f)(11)(i)(B)(2)"],
            }
        return GenerationResult(request.schema.model_validate(data), Usage())


def test_answer_self_corrects_on_verify_failure_with_one_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hit = Hit("8 CFR 214.2(f)(11)(i)(B)(2)", ("OPT",), "Filing window rule.", 0.9)
    monkeypatch.setattr(pipeline, "search", lambda conn, embedder, query, k: [hit])
    monkeypatch.setattr(pipeline, "by_citation", lambda conn, citations: [])
    gen = _SelfCorrectingGenerator()
    services = Services(
        gen, FakeDecisionModel(), FakeEmbedder(), cast(psycopg.Connection, object()), None
    )
    reply = answer("My program ends 2026-05-15, when do I file?", date(2026, 5, 1), services)
    assert reply.rejected_reason is None
    assert reply.explanation.citations == ["8 CFR 214.2(f)(11)(i)(B)(2)"]
    assert len(gen.prompts) == 3
    assert "IMPORTANT CORRECTION:" in gen.prompts[2]


def test_format_provisions_includes_headings_and_match_learned_corrections() -> None:
    formatted = format_provisions(
        (Hit("8 CFR 214.2(f)(12)(ii)(A)", ("OPT", "24-month STEM OPT"), "Report in 10 days.", 0.9),)
    )
    assert "Headings: OPT > 24-month STEM OPT" in formatted
    corrections = load_learned_corrections(Path("data/learned_corrections.json"))
    assert len(corrections) >= 3
    stem_hits = match_learned_corrections("How do I report an interruption to my DSO?", corrections)
    assert any(item.id == "lc-stem-10day-reporting" for item in stem_hits)
    h1b_hits = match_learned_corrections("Am I eligible for H-1B cap-gap?", corrections)
    assert any(item.id == "lc-cap-gap-vs-h1b-scope" for item in h1b_hits)


def test_single_turn_extraction_prompt_is_unchanged() -> None:
    msg = "My program ends 2026-05-15."
    as_of = date(2026, 5, 1)
    baseline = (
        "Extract facts from an F-1 student's message for a rules engine. Today is "
        "2026-05-01. Use ISO dates (YYYY-MM-DD) and resolve relative dates against "
        "today. Leave any fact the student did not state as null; never guess. List each job "
        "the student says they held; set jobs to [] only if the student explicitly says they "
        "have had no jobs, and leave jobs null if they did not mention employment. Never add a "
        "job for a period without work (for example 'unemployed since'). Set a job's "
        "related_to_major and hours_per_week only if the student says them. Never repeat "
        "sensitive personal identifiers (SSN, passport number, A-number, SEVIS ID) in the "
        "restated question. List topics outside F-1 student rules in out_of_scope. Set kind to "
        "greeting for a greeting, thanks or a question about you, unrelated for a message with "
        "nothing to do with US immigration, visas, or studying or working in the US, and "
        "question otherwise.\n\n"
        "Message:\nMy program ends 2026-05-15."
    )
    assert _extraction_prompt(msg, as_of) == baseline
    assert _extraction_prompt(msg, as_of, history=(), prior_facts=StudentFacts()) == baseline


class _FollowUpGenerator:
    model_id = "followup-gen"

    def __init__(self, extraction_payload: dict[str, Any]) -> None:
        self.extraction_payload = extraction_payload
        self.prompts: list[str] = []

    def generate[T: BaseModel](self, request: GenerationRequest[T]) -> GenerationResult[T]:
        self.prompts.append(request.prompt)
        if request.schema is Extraction:
            return GenerationResult(request.schema.model_validate(self.extraction_payload), Usage())
        data = {
            "answerable": True,
            "explanation": "File from 2026-02-14 to 2026-06-14.",
            "citations": ["8 CFR 214.2(f)(11)(i)(B)(2)"],
        }
        return GenerationResult(request.schema.model_validate(data), Usage())


def test_followup_extraction_prompt_includes_prior_facts_and_bounded_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hit = Hit("8 CFR 214.2(f)(11)(i)(B)(2)", ("OPT",), "Filing window rule.", 0.9)
    monkeypatch.setattr(pipeline, "search", lambda conn, embedder, query, k: [hit])
    monkeypatch.setattr(pipeline, "by_citation", lambda conn, citations: [])
    history = [Turn(f"Q{i}", f"A{i}") for i in range(1, MAX_HISTORY_TURNS + 3)]
    prior = StudentFacts(program_end_date=date(2026, 5, 15))
    gen = _FollowUpGenerator(
        {
            "kind": "question",
            "facts": {"program_end_date": "2026-05-15", "opt_recommendation_date": "2026-05-20"},
            "question": "When must I file with that DSO recommendation date?",
        }
    )
    services = Services(
        gen, FakeDecisionModel(), FakeEmbedder(), cast(psycopg.Connection, object()), None
    )
    reply = answer(
        "And my DSO recommended OPT on 2026-05-20",
        date(2026, 5, 1),
        services,
        history=history,
        prior_facts=prior,
    )
    assert reply.rejected_reason is None
    extract_prompt = gen.prompts[0]
    assert "Prior facts:" in extract_prompt
    assert '"program_end_date": "2026-05-15"' in extract_prompt
    assert "Earlier turns:" in extract_prompt
    assert "Q1" not in extract_prompt
    assert "Q2" not in extract_prompt
    assert f"Q{MAX_HISTORY_TURNS + 2}" in extract_prompt


def test_followup_greeting_without_new_facts_uses_fixed_reply_and_preserves_prior_facts() -> None:
    prior = StudentFacts(program_end_date=date(2026, 5, 15))
    gen = _FollowUpGenerator(
        {
            "kind": "greeting",
            "facts": {},
            "question": "Thanks!",
        }
    )
    services = Services(
        gen, FakeDecisionModel(), FakeEmbedder(), cast(psycopg.Connection, object()), None
    )
    reply = answer(
        "Thanks!",
        date(2026, 5, 1),
        services,
        history=[Turn("When must I file?", "File by 2026-06-14.")],
        prior_facts=prior,
    )
    assert len(gen.prompts) == 1
    assert reply.explanation.explanation == FIXED_REPLIES["greeting"]
    assert reply.extraction.facts == prior


def test_check_explanation_still_rejects_dates_injected_only_in_history() -> None:
    fake_history_date = "2028-09-09"
    explanation = _explanation(
        f"You can file by {fake_history_date}.", ["8 CFR 214.2(f)(11)(i)(B)(2)"]
    )
    reason = check_explanation(explanation, _ASSESSMENT, _PROVISIONS)
    assert reason is not None and fake_history_date in reason
