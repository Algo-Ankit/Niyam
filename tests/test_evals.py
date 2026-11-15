import json
from datetime import date
from pathlib import Path

from niyam.assistant.pipeline import Extraction
from niyam.evals.extraction import Item, score, summary
from niyam.evals.extraction import load_items as load_extraction_items
from niyam.evals.retrieval import Ranked, hit_at, load_items, metrics, reciprocal_rank
from niyam.rules.opt import StudentFacts

_ROOT = Path(__file__).parents[1]


def test_hit_at_k_and_reciprocal_rank() -> None:
    ranked = ["a", "b", "c"]
    assert (hit_at(ranked, ["b"], 1), hit_at(ranked, ["b"], 3)) == (0.0, 1.0)
    assert reciprocal_rank(ranked, ["c", "x"]) == 1 / 3
    assert reciprocal_rank(ranked, ["x"]) == 0.0


def test_metrics_average_over_items_per_arm() -> None:
    arms = {"keyword": ["g", "x"], "vector": ["x", "g"], "hybrid": ["x", "y"]}
    scores = metrics([Ranked("1", ("g",), arms), Ranked("2", ("g",), arms)])
    assert scores["keyword"]["hit@1"] == 1.0
    assert scores["vector"]["mrr@10"] == 0.5
    assert scores["hybrid"]["hit@5"] == 0.0


def test_every_gold_paragraph_in_the_eval_set_exists_and_has_text() -> None:
    corpus = json.loads((_ROOT / "data/processed/8-cfr-214.2-f.json").read_text(encoding="utf-8"))
    indexed = {p["citation"] for p in corpus["provisions"] if p["text"]}
    items = load_items(_ROOT / "evals/retrieval.jsonl")
    assert len({i.id for i in items}) == len(items) == 35
    missing = {g for i in items for g in i.gold} - indexed
    assert not missing, missing


def test_extraction_score_compares_fields_scope_and_deadlines() -> None:
    gold = StudentFacts(program_end_date=date(2026, 5, 15))
    item = Item("x", date(2026, 5, 20), "msg", gold, frozenset())
    right = score(item, Extraction(facts=gold, question="q"))
    off_by_a_day = score(
        item, Extraction(facts=StudentFacts(program_end_date=date(2026, 5, 16)), question="q")
    )
    assert (right.wrong_fields, right.deadlines_agree) == ((), True)
    assert (off_by_a_day.wrong_fields, off_by_a_day.deadlines_agree) == (
        ("program_end_date",),
        False,
    )
    assert summary([right, off_by_a_day])["deadlines_agree"] == 0.5


def test_extraction_set_is_well_formed() -> None:
    items = load_extraction_items(_ROOT / "evals/extraction.jsonl")
    assert len({i.id for i in items}) == len(items) == 15
