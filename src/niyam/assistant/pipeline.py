"""One request end to end. Models only extract and explain; every date comes from the rules engine.

Steps: (1) the generator extracts StudentFacts and the question; (2) the rules engine computes
findings; (3) vector search finds candidates, the decision model reranks them, and the top ones
plus the findings' own paragraphs give the provisions; (4) the generator explains using only
those; (5) code rejects any citation or date the model invented.
"""

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Literal

import psycopg
from pydantic import BaseModel, Field

from niyam.config import ThinkingLevel
from niyam.models.errors import ModelError
from niyam.models.interfaces import DecisionModel, Embedder, GenerativeModel
from niyam.models.types import GenerationRequest
from niyam.retrieval import rerank
from niyam.retrieval.store import Hit, by_citation, search
from niyam.rules.opt import Assessment, StudentFacts, assess

OutOfScope = Literal[
    "H-1B lottery, petition or other work visas",
    "green card or permanent residence",
    "taxes",
    "visa stamping or consular renewal",
    "J-1, M-1 or other non-F-1 status",
    "other",
]
NOT_COVERED = (
    "H-1B beyond the cap-gap extension, green card, taxes, visa stamping and consular renewal, "
    "and statuses other than F-1 are not "
    "covered. Your DSO (school international student adviser) or an immigration attorney can help."
)
DISCLAIMER = "Information from 8 CFR 214.2(f), not legal advice. Confirm deadlines with your DSO."
RETRIEVAL_K = 5
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_DAY = r"(?:0?[1-9]|[12]\d|3[01])(?:st|nd|rd|th)?"
_MONTH_CAP = (
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December"
    r"|Jan\.?|Feb\.?|Mar\.?|Apr\.?|Jun\.?|Jul\.?|Aug\.?|Sept?\.?|Oct\.?|Nov\.?|Dec\.?)"
)
_MONTH_ANY = (
    r"(?:[Jj]anuary|[Ff]ebruary|[Mm]arch|[Aa]pril|May|[Jj]une|[Jj]uly|[Aa]ugust"
    r"|[Ss]eptember|[Oo]ctober|[Nn]ovember|[Dd]ecember"
    r"|[Jj]an\.?|[Ff]eb\.?|[Mm]ar\.?|[Aa]pr\.?|[Jj]un\.?|[Jj]ul\.?|[Aa]ug\.?"
    r"|[Ss]ept?\.?|[Oo]ct\.?|[Nn]ov\.?|[Dd]ec\.?)"
)
_WORD_DATE = re.compile(
    rf"\b{_MONTH_ANY} {_DAY}(?:,?\s+\d{{4}})?\b"
    rf"|\b{_DAY} {_MONTH_CAP}(?:,?\s+\d{{4}})?\b"
    r"|\b\d{1,2}/\d{1,2}/\d{2,4}\b"
)
_FULL_MONTH_DATE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)"
    r" (\d{1,2}), (\d{4})\b"
)
_MONTHS: dict[str, int] = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


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
    explanation: Explanation  # the generator's draft; shown only if rejected_reason is None
    rejected_reason: str | None
    rerank_error: str | None  # set when reranking failed and vector order was used instead


@dataclass(frozen=True)
class Services:
    generator: GenerativeModel
    decider: DecisionModel
    embedder: Embedder
    conn: psycopg.Connection
    thinking_level: ThinkingLevel | None


def answer(message: str, as_of: date, services: Services) -> Reply:
    generator, level = services.generator, services.thinking_level
    extraction = extract(message, as_of, generator, level)
    assessment = assess(extraction.facts, as_of)
    candidates = search(services.conn, services.embedder, extraction.question, rerank.CANDIDATES)
    top, rerank_error = top_provisions(services.decider, extraction.question, candidates)
    provisions = _with_cited(services.conn, top, assessment)
    explanation = explain(extraction.question, assessment, provisions, generator, level)
    given = fact_dates(extraction.facts) | {as_of.isoformat()}
    reason = check_explanation(explanation, assessment, provisions, given)
    return Reply(extraction, assessment, provisions, explanation, reason, rerank_error)


def top_provisions(
    decider: DecisionModel, question: str, candidates: list[Hit]
) -> tuple[list[Hit], str | None]:
    """The best `RETRIEVAL_K` candidates after reranking, and the error if reranking failed.

    A reranker failure degrades to vector order instead of failing the reply (D50); the error is
    returned so the reply can say so.
    """
    try:
        ordered = rerank.rerank(decider, question, candidates)
    except ModelError as error:
        return candidates[:RETRIEVAL_K], str(error)
    return ordered[:RETRIEVAL_K], None


def explain(
    question: str,
    assessment: Assessment,
    provisions: tuple[Hit, ...],
    generator: GenerativeModel,
    thinking_level: ThinkingLevel | None,
) -> Explanation:
    """The generator's answer, using only `provisions` and the computed findings."""
    prompt = _explanation_prompt(question, assessment, provisions)
    return _generate(generator, prompt, Explanation, thinking_level)


def fact_dates(facts: StudentFacts) -> frozenset[str]:
    """Every date the student gave, in ISO form; an explanation may repeat these."""
    dates = [getattr(facts, name) for name in StudentFacts.model_fields if name != "jobs"]
    dates += [d for job in (facts.jobs or ()) for d in (job.start, job.end)]
    return frozenset(d.isoformat() for d in dates if isinstance(d, date))


def render(reply: Reply) -> str:
    """The reply exactly as the student sees it."""
    lines = [f"Question: {reply.extraction.question}", ""]
    for finding in reply.assessment.findings:
        lines.append(f"- [{finding.status}] {finding.summary} ({finding.citation})")
        lines.extend(f"    assumption: {a}" for a in finding.assumptions)
    if reply.assessment.missing:
        missing = ", ".join(reply.assessment.missing)
        lines += ["", f"Tell me these to compute more deadlines: {missing}"]
    lines.append("")
    if reply.rejected_reason is None:
        lines.append(reply.explanation.explanation)
        lines.append(f"Sources: {', '.join(reply.explanation.citations)}")
    else:
        lines.append(f"Explanation withheld: it {reply.rejected_reason}.")
    if reply.rerank_error is not None:
        lines.append(f"Note: reranking failed ({reply.rerank_error}); sources are in search order.")
    if reply.extraction.out_of_scope:
        topics = ", ".join(reply.extraction.out_of_scope)
        lines += ["", f"Not covered: {topics}. {NOT_COVERED}"]
    lines += ["", DISCLAIMER]
    return "\n".join(lines)


def extract(
    message: str, as_of: date, generator: GenerativeModel, thinking_level: ThinkingLevel | None
) -> Extraction:
    """The student's facts, question and out-of-scope topics, as the generator reads them."""
    return _generate(generator, _extraction_prompt(message, as_of), Extraction, thinking_level)


def check_explanation(
    explanation: Explanation,
    assessment: Assessment,
    provisions: tuple[Hit, ...],
    given_dates: frozenset[str] = frozenset(),
) -> str | None:
    """Why the explanation must not be shown, or None if every citation and date is grounded.

    Allowed dates: those the rules engine computed, those the student gave (`given_dates`), and
    literal dates written in the given `provisions` (e.g. "April 1" or "September 15, 2026").
    """
    allowed = {p.citation for p in provisions}
    invented = [c for c in explanation.citations if c not in allowed]
    if invented:
        return f"cited provisions it was not given: {invented}"
    provision_words, provision_isos = _provision_dates(provisions)
    known_dates = {
        d.isoformat() for f in assessment.findings for d in (f.opens, f.closes) if d is not None
    }
    known_dates |= set(_ISO_DATE.findall(" ".join(f.summary for f in assessment.findings)))
    known_dates |= given_dates | provision_isos
    bad_words = [
        d for d in _WORD_DATE.findall(explanation.explanation) if d.lower() not in provision_words
    ]
    if bad_words:
        return f"stated dates in a form that cannot be checked: {bad_words}"
    unknown = sorted(set(_ISO_DATE.findall(explanation.explanation)) - known_dates)
    if unknown:
        return f"stated dates the rules engine did not compute: {unknown}"
    return None


def _provision_dates(provisions: tuple[Hit, ...]) -> tuple[set[str], set[str]]:
    """Lowercase word dates and ISO dates appearing literally in the given regulation provisions."""
    words: set[str] = set()
    isos: set[str] = set()
    for provision in provisions:
        words.update(m.lower() for m in _WORD_DATE.findall(provision.body))
        isos.update(_ISO_DATE.findall(provision.body))
        for month, day_s, year_s in _FULL_MONTH_DATE.findall(provision.body):
            try:
                isos.add(date(int(year_s), _MONTHS[month.lower()], int(day_s)).isoformat())
            except ValueError:
                continue
    return words, isos


def _with_cited(
    conn: psycopg.Connection, hits: list[Hit], assessment: Assessment
) -> tuple[Hit, ...]:
    """The findings' paragraphs that retrieval missed, then the retrieved `hits`."""
    cited = [f.citation for f in assessment.findings]
    seen = {h.citation for h in hits}
    extra = by_citation(conn, [c for c in dict.fromkeys(cited) if c not in seen])
    return (*extra, *hits)


def _extraction_prompt(message: str, as_of: date) -> str:
    return (
        "Extract facts from an F-1 student's message for a rules engine. Today is "
        f"{as_of.isoformat()}. Use ISO dates (YYYY-MM-DD) and resolve relative dates against "
        "today. Leave any fact the student did not state as null; never guess. List each job "
        "the student says they held; set jobs to [] only if the student explicitly says they "
        "have had no jobs, and leave jobs null if they did not mention employment. Never add a "
        "job for a period without work (for example 'unemployed since'). Set a job's "
        "related_to_major and hours_per_week only if the student says them. Never repeat "
        "sensitive personal identifiers (SSN, passport number, A-number, SEVIS ID) in the "
        "restated question. List topics outside F-1 student rules in out_of_scope.\n\n"
        f"Message:\n{message}"
    )


def _explanation_prompt(question: str, assessment: Assessment, provisions: tuple[Hit, ...]) -> str:
    findings = [
        {"rule": f.rule, "citation": f.citation, "summary": f.summary, "status": f.status}
        for f in assessment.findings
    ]
    return (
        "You explain US F-1 student rules. Answer the question using ONLY the provisions below "
        "and the computed findings. Rules: cite provisions by their exact bracketed citation; "
        "never compute or state a date that is not in the findings (copy dates exactly, in "
        "YYYY-MM-DD form); if the provisions do not answer the question, set answerable to "
        "false and say what is missing; do not give legal advice.\n\n"
        f"Question: {question}\n\nComputed findings (authoritative):\n"
        f"{json.dumps(findings, indent=1)}\n\nProvisions:\n{format_provisions(provisions)}"
    )


def format_provisions(provisions: tuple[Hit, ...]) -> str:
    """Provisions as the generator and judge see them: bracketed citation, then the text."""
    return "\n\n".join(f"[{p.citation}]\n{p.body}" for p in provisions)


def _generate[T: BaseModel](
    generator: GenerativeModel, prompt: str, schema: type[T], thinking_level: ThinkingLevel | None
) -> T:
    return generator.generate(GenerationRequest(prompt, schema, thinking_level)).output
