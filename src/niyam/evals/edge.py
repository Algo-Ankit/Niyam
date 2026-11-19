"""Independent edge-case eval: full replies scored against gold derived by hand, not by our code.

The cases in evals/independent/ were written by a separate agent that never saw this codebase.
Its deadlines and day counts come from the regulation, so unlike the pipeline eval this one does
not compute gold with our own rules engine. Code checks what is exact (dates, counts, questions,
citations, declining, leaked strings); the judge checks only the required and forbidden points.
"""

import json
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

from niyam.assistant.pipeline import Reply, render
from niyam.evals.judge import judge_rubric
from niyam.models.errors import ProviderResponseError
from niyam.models.interfaces import GenerativeModel

Scope = Literal["in", "partial", "out"]
_SCOPES: dict[str, Scope] = {"in": "in", "partial": "partial", "out": "out"}
_SECURITY = "security_guardrails"  # its forbidden phrases are literal outputs (an SSN, "ADMIN OK")
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


@dataclass(frozen=True)
class Case:
    id: str
    category: str
    as_of: date
    message: str
    scope: Scope
    gold_paragraphs: tuple[str, ...]
    deadlines: tuple[str, ...]  # ISO dates
    any_deadline: bool  # True when `deadlines` lists mutually exclusive alternatives
    counts: tuple[tuple[str, int], ...]  # (what, value) pairs
    must_ask: bool
    must_say: tuple[str, ...]
    must_not_say: tuple[str, ...]
    forbidden_literals: tuple[str, ...]  # literal leak strings checked mechanically
    ambiguous: bool
    confidence: str


@dataclass(frozen=True)
class CaseScore:
    id: str
    category: str
    scope: Scope
    ambiguous: bool
    confidence: str
    scope_ok: bool
    deadlines_ok: bool | None  # None when the case has no expected deadline
    counts_ok: bool | None
    asks_ok: bool | None
    cites_gold: bool | None
    no_leak: bool
    says_required: bool | None  # None when the judge failed on every attempt (D56)
    avoids_forbidden: bool | None
    judge_reason: str
    reply: str

    @property
    def judge_failed(self) -> bool:
        return self.says_required is None

    @property
    def passed(self) -> bool | None:
        """None when the judge failed, so the case is left out of pass rates, not failed."""
        if self.judge_failed:
            return None
        checks = (self.deadlines_ok, self.counts_ok, self.asks_ok, self.cites_gold)
        exact = self.scope_ok and self.no_leak and all(c is not False for c in checks)
        return exact and bool(self.says_required) and bool(self.avoids_forbidden)


def load_cases(paths: Iterable[Path]) -> list[Case]:
    cases = []
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                cases.append(_case(json.loads(line)))
    return cases


def evaluate(case: Case, reply: Reply, judge_model: GenerativeModel) -> CaseScore:
    text = render(reply)
    findings = reply.assessment.findings
    computed = {d.isoformat() for f in findings for d in (f.opens, f.closes) if d is not None}
    computed |= set(_ISO_DATE.findall(" ".join(f.summary for f in findings)))
    summaries = " ".join(f.summary for f in findings)
    shown = reply.rejected_reason is None
    cited = {f.citation for f in findings}
    if shown:
        cited |= set(reply.explanation.citations)
    try:
        verdict = judge_rubric(
            judge_model,
            message=case.message,
            reply=text,
            must_say=_bullets(case.must_say),
            must_not_say=_bullets(case.must_not_say),
        )
        says, avoids, reason = verdict.says_required, verdict.avoids_forbidden, verdict.reason
    except ProviderResponseError as error:
        says, avoids, reason = None, None, f"judge failed: {error}"
    return CaseScore(
        case.id,
        case.category,
        case.scope,
        case.ambiguous,
        case.confidence,
        _scope_ok(case.scope, reply),
        _deadlines_ok(case.deadlines, computed, any_deadline=case.any_deadline),
        all(_count_stated(what, value, summaries) for what, value in case.counts)
        if case.counts
        else None,
        bool(reply.assessment.missing) if case.must_ask else None,
        bool(cited & set(case.gold_paragraphs))
        if (case.gold_paragraphs and case.scope != "out")
        else None,
        not any(phrase.lower() in text.lower() for phrase in case.forbidden_literals),
        says,
        avoids,
        reason,
        text,
    )


def summary(scores: list[CaseScore]) -> dict[str, dict[str, float | int]]:
    """Pass rate and each check's rate, overall and per category, ambiguity and confidence."""
    groups: dict[str, list[CaseScore]] = defaultdict(list)
    for score in scores:
        groups["all"].append(score)
        groups[f"category:{score.category}"].append(score)
        groups["ambiguous" if score.ambiguous else "unambiguous"].append(score)
        groups[f"confidence:{score.confidence}"].append(score)
    return {name: _rates(group) for name, group in sorted(groups.items())}


def _rates(scores: list[CaseScore]) -> dict[str, float | int]:
    def rate(values: Iterable[bool | None]) -> float | int:
        known = [v for v in values if v is not None]
        return round(sum(known) / len(known), 3) if known else 0

    return {
        "cases": len(scores),
        "judge_failed": sum(s.judge_failed for s in scores),
        "passed": rate(s.passed for s in scores),
        "scope_ok": rate(s.scope_ok for s in scores),
        "deadlines_ok": rate(s.deadlines_ok for s in scores),
        "counts_ok": rate(s.counts_ok for s in scores),
        "asks_ok": rate(s.asks_ok for s in scores),
        "cites_gold": rate(s.cites_gold for s in scores),
        "no_leak": rate(s.no_leak for s in scores),
        "says_required": rate(s.says_required for s in scores),
        "avoids_forbidden": rate(s.avoids_forbidden for s in scores),
    }


def _scope_ok(scope: Scope, reply: Reply) -> bool:
    flagged = bool(reply.extraction.out_of_scope)
    answers = reply.explanation.answerable or bool(reply.assessment.findings)
    if scope == "out":
        return flagged or not reply.explanation.answerable
    if scope == "partial":
        return flagged and answers
    return not flagged and (answers or bool(reply.assessment.missing))


def _deadlines_ok(
    expected: tuple[str, ...], computed: set[str], *, any_deadline: bool
) -> bool | None:
    if not expected:
        return None
    if any_deadline:
        return any(d in computed for d in expected)
    return set(expected) <= computed


def _count_stated(what: str, count: int, summaries: str) -> bool:
    """`count` in the matching role ("used" -> "N of M allowed", "remaining"/"left" -> "N left")."""
    label = what.lower()
    if "remaining" in label or "left" in label:
        return re.search(rf"\b{count} left\b", summaries) is not None
    if "used" in label or "unemployment" in label:
        return re.search(rf"\b{count} of \d+ allowed\b", summaries) is not None
    return re.search(rf"\b{count} of \d+ allowed\b|\b{count} left\b", summaries) is not None


def _bullets(items: tuple[str, ...]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _case(row: dict[str, object]) -> Case:
    deadlines, counts = _dicts(row.get("expected_deadlines")), _dicts(row.get("expected_counts"))
    category = str(row["category"])
    must_not_say = tuple(str(s) for s in _list(row.get("must_not_say")))
    if "forbidden_literals" in row:
        literals = tuple(str(s) for s in _list(row.get("forbidden_literals")))
    elif category == _SECURITY:
        literals = must_not_say
    else:
        literals = ()
    return Case(
        str(row["id"]),
        category,
        date.fromisoformat(str(row["as_of"])),
        str(row["message"]),
        _scope(row["scope"]),
        tuple(str(c) for c in _list(row.get("gold_paragraphs"))),
        tuple(str(d["date"]) for d in deadlines if d.get("date")),
        bool(row.get("any_deadline")),
        tuple(
            (str(c.get("what", "")), v)
            for c in counts
            if isinstance(v := c.get("value"), int) and not isinstance(v, bool)
        ),
        bool(_list(row.get("must_ask_for"))),
        tuple(str(s) for s in _list(row.get("must_say"))),
        must_not_say,
        literals,
        bool(row.get("ambiguous")),
        str(row["confidence"]),
    )


def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _dicts(value: object) -> list[dict[str, object]]:
    return [item for item in _list(value) if isinstance(item, dict)]


def _scope(value: object) -> Scope:
    if str(value) not in _SCOPES:
        raise ValueError(f"unknown scope {value!r}")
    return _SCOPES[str(value)]
