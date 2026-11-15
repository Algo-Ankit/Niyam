"""Whole-pipeline eval: a student's message in, the full reply scored against the scenario.

Three kinds of scenario: in scope (the reply must show a correct, grounded explanation citing
the gold paragraph, with exact deadlines), unanswerable (the generator must say the provisions
do not answer it), and out of scope (the topic must be flagged as not covered).
"""

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

from niyam.assistant.pipeline import Reply, format_provisions
from niyam.evals.extraction import findings_signature
from niyam.evals.judge import judge
from niyam.models.interfaces import GenerativeModel
from niyam.rules.opt import StudentFacts

Kind = Literal["in_scope", "unanswerable", "out_of_scope"]
_KIND_BY_ANSWERABLE: dict[bool | None, Kind] = {
    True: "in_scope",
    False: "unanswerable",
    None: "out_of_scope",
}


@dataclass(frozen=True)
class Scenario:
    id: str
    as_of: date
    message: str
    facts: StudentFacts
    out_of_scope: frozenset[str]
    kind: Kind
    gold: tuple[str, ...]
    reference: str


@dataclass(frozen=True)
class ScenarioScore:
    id: str
    kind: Kind
    scope_correct: bool
    has_deadlines: bool
    deadlines_agree: bool
    model_answerable: bool
    shown: bool
    cites_gold: bool
    correct: bool | None  # judged for in-scope scenarios only
    grounded: bool | None
    rejected_reason: str | None
    answer: str


def load_scenarios(path: Path) -> list[Scenario]:
    scenarios = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        kind = _KIND_BY_ANSWERABLE[row["answerable"]]
        scenarios.append(
            Scenario(
                row["id"],
                date.fromisoformat(row["as_of"]),
                row["message"],
                StudentFacts.model_validate(row["facts"]),
                frozenset(row["out_of_scope"]),
                kind,
                tuple(row["gold"]),
                row["reference"],
            )
        )
    return scenarios


def evaluate(scenario: Scenario, reply: Reply, judge_model: GenerativeModel) -> ScenarioScore:
    gold_findings = findings_signature(scenario.facts, scenario.as_of)
    explanation = reply.explanation
    shown = reply.rejected_reason is None
    correct = grounded = None
    if scenario.kind == "in_scope":
        findings = "\n".join(f"{f.summary} ({f.citation})" for f in reply.assessment.findings)
        verdict = judge(
            judge_model,
            question=scenario.message,
            reference=scenario.reference,
            answer=explanation.explanation,
            provisions=format_provisions(reply.provisions),
            findings=findings,
        )
        # A withheld explanation never reaches the student, so it cannot count as correct.
        correct, grounded = verdict.correct and shown, verdict.grounded and shown
    return ScenarioScore(
        scenario.id,
        scenario.kind,
        frozenset(reply.extraction.out_of_scope) == scenario.out_of_scope,
        bool(gold_findings),
        findings_signature(reply.extraction.facts, scenario.as_of) == gold_findings,
        explanation.answerable,
        shown,
        bool(set(explanation.citations) & set(scenario.gold)),
        correct,
        grounded,
        reply.rejected_reason,
        explanation.explanation,
    )


def summary(scores: list[ScenarioScore]) -> dict[str, float | int]:
    in_scope = [s for s in scores if s.kind == "in_scope"]
    unanswerable = [s for s in scores if s.kind == "unanswerable"]
    with_deadlines = [s for s in scores if s.has_deadlines]
    return {
        "scenarios": len(scores),
        "scope_correct": _rate(s.scope_correct for s in scores),
        "deadlines_agree": _rate(s.deadlines_agree for s in with_deadlines),
        "in_scope_shown": _rate(s.shown for s in in_scope),
        "in_scope_cites_gold": _rate(s.cites_gold for s in in_scope),
        "in_scope_correct": _rate(bool(s.correct) for s in in_scope),
        "in_scope_grounded": _rate(bool(s.grounded) for s in in_scope),
        "unanswerable_abstained": _rate(not s.model_answerable for s in unanswerable),
    }


def _rate(values: Iterable[bool]) -> float:
    flags = list(values)
    return round(sum(flags) / len(flags), 3) if flags else 0.0
