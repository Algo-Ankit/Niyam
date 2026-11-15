"""Extraction eval: fields, out-of-scope topics, and whether the deadlines come out right.

The headline is deadline agreement: the rules engine is run on the extracted facts and on the
gold facts, and the two sets of findings must match exactly.
"""

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from niyam.assistant.pipeline import Extraction
from niyam.rules.opt import StudentFacts, assess

SCALAR_FIELDS = tuple(name for name in StudentFacts.model_fields if name != "jobs")


@dataclass(frozen=True)
class Item:
    id: str
    as_of: date
    message: str
    facts: StudentFacts
    out_of_scope: frozenset[str]


@dataclass(frozen=True)
class Score:
    id: str
    wrong_fields: tuple[str, ...]  # scalar fields plus "jobs"
    out_of_scope_correct: bool
    has_deadlines: bool  # the gold facts produce at least one finding
    deadlines_agree: bool


def load_items(path: Path) -> list[Item]:
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            items.append(
                Item(
                    row["id"],
                    date.fromisoformat(row["as_of"]),
                    row["message"],
                    StudentFacts.model_validate(row["facts"]),
                    frozenset(row["out_of_scope"]),
                )
            )
    return items


def score(item: Item, extraction: Extraction) -> Score:
    got = extraction.facts
    wrong = [f for f in SCALAR_FIELDS if getattr(got, f) != getattr(item.facts, f)]
    if _job_spans(got) != _job_spans(item.facts):
        wrong.append("jobs")
    gold = _findings(item.facts, item.as_of)
    return Score(
        item.id,
        tuple(wrong),
        frozenset(extraction.out_of_scope) == item.out_of_scope,
        bool(gold),
        _findings(got, item.as_of) == gold,
    )


def summary(scores: list[Score]) -> dict[str, float]:
    count = len(scores)
    fields = len(SCALAR_FIELDS) + 1
    with_deadlines = [s for s in scores if s.has_deadlines]
    return {
        "field_accuracy": round(1 - sum(len(s.wrong_fields) for s in scores) / (count * fields), 3),
        "all_fields_correct": round(sum(not s.wrong_fields for s in scores) / count, 3),
        "out_of_scope_correct": round(sum(s.out_of_scope_correct for s in scores) / count, 3),
        "deadlines_agree": round(
            sum(s.deadlines_agree for s in with_deadlines) / len(with_deadlines), 3
        ),
        "items_with_deadlines": len(with_deadlines),
    }


def _job_spans(facts: StudentFacts) -> list[tuple[date, date | None]]:
    return sorted((job.start, job.end) for job in facts.jobs)


def _findings(facts: StudentFacts, as_of: date) -> list[tuple[str, str, date | None, date | None]]:
    """Employer names are left out: they appear in summaries but never change a date."""
    unnamed = facts.model_copy(
        update={"jobs": [job.model_copy(update={"employer": ""}) for job in facts.jobs]}
    )
    return [(f.rule, f.status, f.opens, f.closes) for f in assess(unnamed, as_of).findings]
