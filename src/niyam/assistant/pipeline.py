"""One request end to end. Models only extract and explain; every date comes from the rules engine.

Steps: (1) the generator extracts StudentFacts and the question; (2) the rules engine computes
findings; (3) hybrid search plus the findings' own paragraphs give the provisions; (4) the
generator explains using only those; (5) code rejects any citation or date the model invented.
"""

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Literal

import psycopg
from pydantic import BaseModel, Field

from niyam.config import ThinkingLevel
from niyam.models.interfaces import Embedder, GenerativeModel
from niyam.models.types import GenerationRequest
from niyam.retrieval.store import Hit, by_citation, search
from niyam.rules.opt import Assessment, StudentFacts, assess

OutOfScope = Literal[
    "H-1B or other work visas",
    "green card or permanent residence",
    "taxes",
    "travel, visa stamping or re-entry",
    "J-1, M-1 or other non-F-1 status",
    "other",
]
NOT_COVERED = (
    "H-1B, green card, taxes, travel and visa stamping, and statuses other than F-1 are not "
    "covered. Your DSO (school international student adviser) or an immigration attorney can help."
)
DISCLAIMER = "Information from 8 CFR 214.2(f), not legal advice. Confirm deadlines with your DSO."
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_WORD_DATE = re.compile(
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.? \d{1,2}\b"
    r"|\b\d{1,2}/\d{1,2}/\d{2,4}\b"
)


class Extraction(BaseModel):
    facts: StudentFacts
    question: str = Field(description="The student's question, restated in one sentence")
    out_of_scope: list[OutOfScope] = Field(
        default_factory=list, description="Topics in the message that are outside F-1 rules"
    )


class Explanation(BaseModel):
    answerable: bool = Field(description="False if the provisions do not answer the question")
    explanation: str = Field(description="Plain-language answer, at most 150 words")
    citations: list[str] = Field(description="Citations of the provisions the answer relies on")


@dataclass(frozen=True)
class Reply:
    extraction: Extraction
    assessment: Assessment
    provisions: tuple[Hit, ...]
    explanation: Explanation | None  # None when it failed the citation or date check
    rejected_reason: str | None


@dataclass(frozen=True)
class Services:
    generator: GenerativeModel
    embedder: Embedder
    conn: psycopg.Connection
    thinking_level: ThinkingLevel | None


def answer(message: str, as_of: date, services: Services) -> Reply:
    generator, level = services.generator, services.thinking_level
    extraction = _generate(generator, _extraction_prompt(message, as_of), Extraction, level)
    assessment = assess(extraction.facts, as_of)
    provisions = _provisions(services.conn, services.embedder, extraction.question, assessment)
    explanation = _generate(
        generator,
        _explanation_prompt(extraction.question, assessment, provisions),
        Explanation,
        level,
    )
    reason = check_explanation(explanation, assessment, provisions)
    return Reply(extraction, assessment, provisions, None if reason else explanation, reason)


def check_explanation(
    explanation: Explanation, assessment: Assessment, provisions: tuple[Hit, ...]
) -> str | None:
    """Why the explanation must not be shown, or None if every citation and date is grounded."""
    allowed = {p.citation for p in provisions}
    invented = [c for c in explanation.citations if c not in allowed]
    if invented:
        return f"cited provisions it was not given: {invented}"
    known_dates = {
        d.isoformat() for f in assessment.findings for d in (f.opens, f.closes) if d is not None
    }
    known_dates |= set(_ISO_DATE.findall(" ".join(f.summary for f in assessment.findings)))
    if word_dates := _WORD_DATE.findall(explanation.explanation):
        return f"stated dates in a form that cannot be checked: {word_dates}"
    unknown = sorted(set(_ISO_DATE.findall(explanation.explanation)) - known_dates)
    if unknown:
        return f"stated dates the rules engine did not compute: {unknown}"
    return None


def _provisions(
    conn: psycopg.Connection, embedder: Embedder, question: str, assessment: Assessment
) -> tuple[Hit, ...]:
    hits = search(conn, embedder, question, k=6)
    cited = [f.citation for f in assessment.findings]
    seen = {h.citation for h in hits}
    extra = by_citation(conn, [c for c in dict.fromkeys(cited) if c not in seen])
    return (*extra, *hits)


def _extraction_prompt(message: str, as_of: date) -> str:
    return (
        "Extract facts from an F-1 student's message for a rules engine. Today is "
        f"{as_of.isoformat()}. Use ISO dates (YYYY-MM-DD) and resolve relative dates against "
        "today. Leave any fact the student did not state as null; never guess. List each job "
        "the student mentions. List topics outside F-1 student rules in out_of_scope.\n\n"
        f"Message:\n{message}"
    )


def _explanation_prompt(question: str, assessment: Assessment, provisions: tuple[Hit, ...]) -> str:
    findings = [
        {"rule": f.rule, "citation": f.citation, "summary": f.summary, "status": f.status}
        for f in assessment.findings
    ]
    passages = "\n\n".join(f"[{p.citation}]\n{p.body}" for p in provisions)
    return (
        "You explain US F-1 student rules. Answer the question using ONLY the provisions below "
        "and the computed findings. Rules: cite provisions by their exact bracketed citation; "
        "never compute or state a date that is not in the findings (copy dates exactly, in "
        "YYYY-MM-DD form); if the provisions do not answer the question, set answerable to "
        "false and say what is missing; do not give legal advice.\n\n"
        f"Question: {question}\n\nComputed findings (authoritative):\n"
        f"{json.dumps(findings, indent=1)}\n\nProvisions:\n{passages}"
    )


def _generate[T: BaseModel](
    generator: GenerativeModel, prompt: str, schema: type[T], thinking_level: ThinkingLevel | None
) -> T:
    return generator.generate(GenerationRequest(prompt, schema, thinking_level)).output
