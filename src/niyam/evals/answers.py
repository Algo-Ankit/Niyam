"""Answer-quality eval: given the gold provisions, is the generated answer correct and grounded?

Retrieval is taken out of the loop (the gold paragraphs are passed directly), so this measures
generation alone. Items are the retrieval dev questions that carry a reference answer.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from niyam.assistant.pipeline import check_explanation, explain, format_provisions
from niyam.config import ThinkingLevel
from niyam.evals.judge import judge
from niyam.models.interfaces import GenerativeModel
from niyam.retrieval.store import Hit
from niyam.rules.opt import Assessment

_NO_FINDINGS = Assessment((), ())


@dataclass(frozen=True)
class AnswerItem:
    id: str
    question: str
    gold: tuple[str, ...]
    reference: str


@dataclass(frozen=True)
class AnswerScore:
    id: str
    answerable: bool  # the generator said the provisions answer the question
    shown: bool  # passed the citation and date check
    cites_gold: bool
    correct: bool
    grounded: bool
    judge_reason: str
    answer: str


def load_items(path: Path) -> list[AnswerItem]:
    """The rows of a retrieval set that have a reference answer."""
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and "reference" in (row := json.loads(line)):
            items.append(
                AnswerItem(row["id"], row["question"], tuple(row["gold"]), row["reference"])
            )
    return items


def corpus_hits(corpus_file: Path) -> dict[str, Hit]:
    """Every provision with text, as a Hit, keyed by citation."""
    corpus = json.loads(corpus_file.read_text(encoding="utf-8"))
    return {
        p["citation"]: Hit(p["citation"], tuple(p["headings"]), p["text"], 0.0)
        for p in corpus["provisions"]
        if p["text"]
    }


def evaluate(
    item: AnswerItem,
    hits: dict[str, Hit],
    generator: GenerativeModel,
    judge_model: GenerativeModel,
    thinking_level: ThinkingLevel | None,
) -> AnswerScore:
    provisions = tuple(hits[c] for c in item.gold)
    explanation = explain(item.question, _NO_FINDINGS, provisions, generator, thinking_level)
    rejected = check_explanation(explanation, _NO_FINDINGS, provisions)
    verdict = judge(
        judge_model,
        question=item.question,
        reference=item.reference,
        answer=explanation.explanation,
        provisions=format_provisions(provisions),
        findings="",
    )
    return AnswerScore(
        item.id,
        explanation.answerable,
        rejected is None,
        bool(set(explanation.citations) & set(item.gold)),
        verdict.correct,
        verdict.grounded,
        verdict.reason,
        explanation.explanation,
    )


def summary(scores: list[AnswerScore]) -> dict[str, float]:
    count = len(scores)
    return {
        name: round(sum(getattr(s, name) for s in scores) / count, 3)
        for name in ("answerable", "shown", "cites_gold", "correct", "grounded")
    }
