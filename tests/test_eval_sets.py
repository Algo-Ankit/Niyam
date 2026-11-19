"""Eval sets stay well formed, and the end-to-end scorer counts what it claims to."""

import json
from datetime import date
from pathlib import Path

from pydantic import BaseModel

from niyam.assistant.pipeline import Explanation, Extraction, Reply
from niyam.evals import answers, end_to_end, retrieval
from niyam.evals.retrieval import Ranked
from niyam.evals.stats import paired_bootstrap
from niyam.models.types import GenerationRequest, GenerationResult, Usage
from niyam.retrieval.store import Hit
from niyam.rules.opt import StudentFacts, assess

_ROOT = Path(__file__).parents[1]
_CORPUS = _ROOT / "data/processed/8-cfr-214.2-f.json"


class _Judge:
    """Always returns the verdict it was built with."""

    model_id = "fake-judge"

    def __init__(self, correct: bool) -> None:
        self._correct = correct

    def generate[T: BaseModel](self, request: GenerationRequest[T]) -> GenerationResult[T]:
        verdict = {"correct": self._correct, "grounded": True, "reason": "fake"}
        return GenerationResult(request.schema.model_validate(verdict), Usage())


def _indexed() -> set[str]:
    corpus = json.loads(_CORPUS.read_text(encoding="utf-8"))
    return {p["citation"] for p in corpus["provisions"] if p["text"]}


def test_paired_bootstrap_brackets_the_mean_difference() -> None:
    interval = paired_bootstrap([0.0] * 10 + [1.0] * 10, [1.0] * 20)
    assert interval.mean == 0.5
    assert interval.low <= 0.5 <= interval.high
    assert interval.excludes_zero
    assert not paired_bootstrap([1.0, 0.0], [0.0, 1.0]).excludes_zero


def test_comparisons_are_against_the_vector_arm() -> None:
    arms = {"keyword": ["x", "g"], "vector": ["g"], "hybrid": ["g"]}
    result = retrieval.comparisons([Ranked("1", ("g",), arms)] * 5)
    assert set(result) == {"keyword", "hybrid"}
    assert result["keyword"]["hit@1"].mean == -1.0


def test_dev_and_test_sets_have_distinct_ids_and_real_gold_paragraphs() -> None:
    dev = retrieval.load_items(_ROOT / "evals/retrieval-dev.jsonl")
    test = retrieval.load_items(_ROOT / "evals/retrieval-test.jsonl")
    assert (len(dev), len(test)) == (60, 35)
    assert not {i.id for i in dev} & {i.id for i in test}
    assert not {g for i in dev + test for g in i.gold} - _indexed()


def test_answer_set_is_the_40_dev_questions_with_references() -> None:
    items = answers.load_items(_ROOT / "evals/retrieval-dev.jsonl")
    assert len(items) == 40
    assert all(i.reference for i in items)
    assert not {c for i in items for c in i.context} - _indexed()
    by_id = {i.id: i for i in items}
    assert by_id["d26"].gold == ("8 CFR 214.2(f)(4)",)
    assert by_id["d26"].context == ("8 CFR 214.2(f)(4)(i)", "8 CFR 214.2(f)(4)(ii)")


def test_pipeline_set_mix_and_gold_paragraphs() -> None:
    scenarios = end_to_end.load_scenarios(_ROOT / "evals/pipeline.jsonl")
    kinds = [s.kind for s in scenarios]
    assert (kinds.count("in_scope"), kinds.count("unanswerable"), kinds.count("out_of_scope")) == (
        30,
        4,
        6,
    )
    assert not {g for s in scenarios for g in s.gold} - _indexed()
    assert all(s.reference and s.gold for s in scenarios if s.kind == "in_scope")


def _reply(facts: StudentFacts, as_of: date, rejected: str | None) -> Reply:
    explanation = Explanation(
        answerable=True,
        explanation="File by 2026-06-14.",
        citations=["8 CFR 214.2(f)(11)(i)(B)(2)"],
    )
    provisions = (Hit("8 CFR 214.2(f)(11)(i)(B)(2)", (), "text", 0.0),)
    extraction = Extraction(facts=facts, question="q")
    return Reply(extraction, assess(facts, as_of), provisions, explanation, rejected, None)


def test_end_to_end_score_counts_a_withheld_explanation_as_not_correct() -> None:
    scenario = end_to_end.load_scenarios(_ROOT / "evals/pipeline.jsonl")[0]
    shown = end_to_end.evaluate(
        scenario, _reply(scenario.facts, scenario.as_of, None), _Judge(correct=True)
    )
    withheld = end_to_end.evaluate(
        scenario, _reply(scenario.facts, scenario.as_of, "invented a date"), _Judge(correct=True)
    )
    assert (shown.correct, shown.cites_gold, shown.deadlines_agree) == (True, True, True)
    assert (withheld.shown, withheld.correct) == (False, False)
    totals = end_to_end.summary([shown, withheld])
    assert totals["in_scope_correct"] == 0.5
