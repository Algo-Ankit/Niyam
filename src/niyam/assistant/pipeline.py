"""One request end to end. Models only extract and explain; every date comes from the rules engine.

A greeting or unrelated message that states no facts gets a fixed reply after step 1 (D72).

Steps: (1) the generator extracts StudentFacts and the question; (2) the rules engine computes
findings; (3) vector search finds candidates, the decision model reranks them, and the top ones
plus the findings' own paragraphs give the provisions; (4) the generator explains using only
those; (5) code rejects any citation or date the model invented.
"""

import json
import re
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Literal, get_args

import psycopg
from pydantic import BaseModel, Field

from niyam.assistant.tracing import NO_TRACING, Trace, TraceDetails, Tracer
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
Kind = Literal["question", "greeting", "unrelated"]
_COVERAGE = (
    "post-completion OPT, the STEM OPT extension, OPT unemployment limits and the H-1B cap-gap "
    "extension"
)
_EXAMPLES = (
    'For example: "My program ends 2027-05-15. When can I apply for OPT?" or "I started OPT on '
    "2026-07-01 and have been unemployed since 2026-09-01. How many unemployment days do I have "
    'left?"'
)
FIXED_REPLIES: dict[Literal["greeting", "unrelated"], str] = {
    "greeting": (
        "Hi, I'm Niyam. I answer questions about F-1 student work rules in 8 CFR 214.2(f): "
        f"{_COVERAGE}. Tell me your dates, such as your program end date, OPT dates and jobs, "
        "and I compute your deadlines with a rules engine and show the regulation text they "
        f"come from. {_EXAMPLES}"
    ),
    "unrelated": f"I can only help with F-1 student work rules: {_COVERAGE}. {_EXAMPLES}",
}
Stage = Literal["extract", "rules", "retrieve", "rerank", "explain", "verify"]
STAGES: tuple[Stage, ...] = get_args(Stage)
StageCallback = Callable[[Stage, int], None]  # (stage, elapsed milliseconds)
RETRIEVAL_K = 5
LEARNED_CORRECTIONS_PATH = Path("data/learned_corrections.json")
RETRY_BUDGET_SECONDS = 25.0
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
_WRITTEN_MONTH_DAY_YEAR = re.compile(
    rf"\b({_MONTH_ANY}) (0?[1-9]|[12]\d|3[01])(?:st|nd|rd|th)?,?\s+(\d{{4}})\b"
)
_WRITTEN_DAY_MONTH_YEAR = re.compile(
    rf"\b(0?[1-9]|[12]\d|3[01])(?:st|nd|rd|th)? ({_MONTH_CAP}),?\s+(\d{{4}})\b"
)
_MONTHS: dict[str, int] = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}


class Extraction(BaseModel):
    kind: Kind = Field(
        default="question",
        description="greeting: a greeting, thanks, or a question about the assistant itself; "
        "unrelated: nothing to do with US immigration, visas, or studying or working in the US; "
        "question: everything else",
    )
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
class LearnedCorrection:
    """Verified guidance harvested from failures or audits, pinned by keyword match (D77)."""

    id: str
    keywords: tuple[str, ...]
    required_citations: tuple[str, ...]
    guidance: str
    source_trace_id: str | None = None


def load_learned_corrections(
    path: Path = LEARNED_CORRECTIONS_PATH,
) -> tuple[LearnedCorrection, ...]:
    """Load learned corrections from `path`, returning `()` if absent or unreadable."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    if not isinstance(raw, list):
        return ()
    items: list[LearnedCorrection] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        cid = str(row.get("id", "")).strip()
        guidance = str(row.get("guidance", "")).strip()
        keywords = tuple(str(k).strip().lower() for k in row.get("keywords", ()) if str(k).strip())
        citations = tuple(
            str(c).strip() for c in row.get("required_citations", ()) if str(c).strip()
        )
        source_trace = row.get("source_trace_id")
        if cid and guidance and keywords:
            items.append(
                LearnedCorrection(
                    id=cid,
                    keywords=keywords,
                    required_citations=citations,
                    guidance=guidance,
                    source_trace_id=str(source_trace) if source_trace else None,
                )
            )
    return tuple(items)


def match_learned_corrections(
    question: str, corrections: Sequence[LearnedCorrection], limit: int = 3
) -> tuple[LearnedCorrection, ...]:
    """Return up to `limit` corrections matching `question`, ordered by keyword hits."""
    lowered = question.lower()
    scored: list[tuple[int, int, LearnedCorrection]] = []
    for index, correction in enumerate(corrections):
        hits = sum(1 for kw in correction.keywords if kw in lowered)
        if hits > 0:
            scored.append((hits, -index, correction))
    scored.sort(key=lambda entry: (entry[0], entry[1]), reverse=True)
    return tuple(entry[2] for entry in scored[:limit])


@dataclass(frozen=True)
class Reply:
    extraction: Extraction
    assessment: Assessment
    provisions: tuple[Hit, ...]
    explanation: Explanation  # the generator's draft; shown only if rejected_reason is None
    rejected_reason: str | None
    rerank_error: str | None  # set when reranking failed and vector order was used instead
    trace_id: str | None = None


@dataclass(frozen=True)
class Services:
    generator: GenerativeModel
    decider: DecisionModel
    embedder: Embedder
    conn: psycopg.Connection
    thinking_level: ThinkingLevel | None
    tracer: Tracer = NO_TRACING


def answer(
    message: str, as_of: date, services: Services, on_stage: StageCallback | None = None
) -> Reply:
    """The full reply; `on_stage(stage, ms)` is called as each of `STAGES` finishes."""
    with services.tracer.trace() as trace:
        reply = _answer(message, as_of, services, _StageTimer(on_stage, trace))
        shown = reply.rejected_reason is None
        details = TraceDetails(
            kind=reply.extraction.kind,
            out_of_scope=tuple(reply.extraction.out_of_scope),
            withheld_reason=reply.rejected_reason,
            cited_provisions=tuple(reply.explanation.citations if shown else ()),
            findings_summaries=tuple(
                f"{f.summary} ({f.citation})" for f in reply.assessment.findings
            ),
            explanation=reply.explanation.explanation if shown else None,
        )
        trace.finish(
            withheld=not shown,
            rerank_failed=reply.rerank_error is not None,
            findings=len(reply.assessment.findings),
            details=details,
        )
        return replace(reply, trace_id=trace.trace_id)


def _answer(message: str, as_of: date, services: Services, stage: "_StageTimer") -> Reply:
    started = time.perf_counter()
    generator, level = services.generator, services.thinking_level
    with stage("extract"):
        extraction = extract(message, as_of, generator, level)
    stage.trace.question(extraction.question, as_of)
    if extraction.kind != "question" and not states_facts(extraction.facts):
        return fixed_reply(extraction, extraction.kind)
    matched = match_learned_corrections(extraction.question, load_learned_corrections())
    extra_citations = [c for item in matched for c in item.required_citations]
    guidance = tuple(item.guidance for item in matched)
    with stage("rules"):
        assessment = assess(extraction.facts, as_of)
    with stage("retrieve"):
        candidates = search(
            services.conn, services.embedder, extraction.question, rerank.CANDIDATES
        )
    with stage("rerank"):
        top, rerank_error = top_provisions(services.decider, extraction.question, candidates)
        provisions = _with_cited(services.conn, top, assessment, extra_citations)
    with stage("explain"):
        explanation = explain(
            extraction.question, assessment, provisions, generator, level, guidance=guidance
        )
    with stage("verify"):
        given = fact_dates(extraction.facts) | {as_of.isoformat()}
        explanation, reason = _verify_or_self_correct(
            explanation,
            question=extraction.question,
            assessment=assessment,
            provisions=provisions,
            given=given,
            services=services,
            guidance=guidance,
            started=started,
        )
    return Reply(extraction, assessment, provisions, explanation, reason, rerank_error)


def _verify_or_self_correct(  # noqa: PLR0913  # encapsulates Layer 1 repair + 1-shot retry
    explanation: Explanation,
    *,
    question: str,
    assessment: Assessment,
    provisions: tuple[Hit, ...],
    given: frozenset[str],
    services: Services,
    guidance: tuple[str, ...],
    started: float,
) -> tuple[Explanation, str | None]:
    repaired = repair_explanation(explanation, assessment, provisions, given)
    reason = check_explanation(repaired, assessment, provisions, given)
    if reason is not None and (time.perf_counter() - started) < RETRY_BUDGET_SECONDS:
        try:
            retried = explain(
                question,
                assessment,
                provisions,
                services.generator,
                services.thinking_level,
                guidance=guidance,
                rejection_reason=reason,
            )
        except ModelError:
            return repaired, reason
        retried_repaired = repair_explanation(retried, assessment, provisions, given)
        retried_reason = check_explanation(retried_repaired, assessment, provisions, given)
        if retried_reason is None:
            return retried_repaired, None
        return retried_repaired, retried_reason
    return repaired, reason


class _StageTimer:
    """Traces and times a block; reports it to the callback only if the block finished."""

    def __init__(self, on_stage: StageCallback | None, trace: Trace) -> None:
        self._on_stage = on_stage
        self.trace = trace

    @contextmanager
    def __call__(self, name: Stage) -> Iterator[None]:
        start = time.perf_counter()
        with self.trace.stage(name):
            yield
        if self._on_stage is not None:
            self._on_stage(name, round((time.perf_counter() - start) * 1000))


def states_facts(facts: StudentFacts) -> bool:
    """Whether the student gave any fact; such a message always takes the full pipeline."""
    return any(value is not None for value in facts.model_dump().values())


def fixed_reply(extraction: Extraction, kind: Literal["greeting", "unrelated"]) -> Reply:
    """The builder-written reply for a message that is not a question (D72)."""
    explanation = Explanation(answerable=True, explanation=FIXED_REPLIES[kind], citations=[])
    return Reply(extraction, Assessment((), ()), (), explanation, None, None)


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


def explain(  # noqa: PLR0913  # optional learned guidance and retry rejection reason
    question: str,
    assessment: Assessment,
    provisions: tuple[Hit, ...],
    generator: GenerativeModel,
    thinking_level: ThinkingLevel | None,
    *,
    guidance: Sequence[str] = (),
    rejection_reason: str | None = None,
) -> Explanation:
    """The generator's answer, using only `provisions`, computed findings, and optional guidance."""
    prompt = _explanation_prompt(question, assessment, provisions, guidance, rejection_reason)
    return _generate(generator, prompt, Explanation, thinking_level)


def repair_explanation(
    explanation: Explanation,
    assessment: Assessment,
    provisions: tuple[Hit, ...],
    given_dates: frozenset[str] = frozenset(),
) -> Explanation:
    """Deterministically normalize bracketed citations and already-known written dates (D77)."""
    cleaned_citations = list(
        dict.fromkeys(c.strip().strip("[]").strip() for c in explanation.citations if c.strip())
    )
    provision_words, _ = _provision_dates(provisions)
    known = _known_dates(assessment, given_dates)

    def _replace_mdy(match: re.Match[str]) -> str:
        raw = match.group(0)
        if raw.lower() in provision_words:
            return raw
        return _iso_if_known(match.group(1), match.group(2), match.group(3), known) or raw

    def _replace_dmy(match: re.Match[str]) -> str:
        raw = match.group(0)
        if raw.lower() in provision_words:
            return raw
        return _iso_if_known(match.group(2), match.group(1), match.group(3), known) or raw

    text = _WRITTEN_MONTH_DAY_YEAR.sub(_replace_mdy, explanation.explanation)
    text = _WRITTEN_DAY_MONTH_YEAR.sub(_replace_dmy, text)
    return explanation.model_copy(update={"citations": cleaned_citations, "explanation": text})


def _iso_if_known(month_s: str, day_s: str, year_s: str, known: set[str]) -> str | None:
    month = _MONTHS.get(month_s.rstrip(".").lower())
    if month is None:
        return None
    try:
        iso = date(int(year_s), month, int(day_s)).isoformat()
    except ValueError:
        return None
    return iso if iso in known else None


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
        if reply.explanation.citations:
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
    known_dates = _known_dates(assessment, given_dates) | provision_isos
    bad_words = [
        d for d in _WORD_DATE.findall(explanation.explanation) if d.lower() not in provision_words
    ]
    if bad_words:
        return f"stated dates in a form that cannot be checked: {bad_words}"
    unknown = sorted(set(_ISO_DATE.findall(explanation.explanation)) - known_dates)
    if unknown:
        return f"stated dates the rules engine did not compute: {unknown}"
    return None


def _known_dates(assessment: Assessment, given_dates: frozenset[str]) -> set[str]:
    known = {
        d.isoformat() for f in assessment.findings for d in (f.opens, f.closes) if d is not None
    }
    known |= set(_ISO_DATE.findall(" ".join(f.summary for f in assessment.findings)))
    return known | set(given_dates)


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
    conn: psycopg.Connection,
    hits: list[Hit],
    assessment: Assessment,
    extra_citations: Sequence[str] = (),
) -> tuple[Hit, ...]:
    """The findings' and learned-correction paragraphs missed by retrieval, then `hits`."""
    cited = [f.citation for f in assessment.findings] + list(extra_citations)
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
        "restated question. List topics outside F-1 student rules in out_of_scope. Set kind to "
        "greeting for a greeting, thanks or a question about you, unrelated for a message with "
        "nothing to do with US immigration, visas, or studying or working in the US, and "
        "question otherwise.\n\n"
        f"Message:\n{message}"
    )


def _explanation_prompt(
    question: str,
    assessment: Assessment,
    provisions: tuple[Hit, ...],
    guidance: Sequence[str] = (),
    rejection_reason: str | None = None,
) -> str:
    findings = [
        {"rule": f.rule, "citation": f.citation, "summary": f.summary, "status": f.status}
        for f in assessment.findings
    ]
    blocks = [
        "You explain US F-1 student rules. Answer the question using ONLY the provisions below "
        "and the computed findings. Rules: cite provisions by their exact bracketed citation; "
        "never compute or state a date that is not in the findings (copy dates exactly, in "
        "YYYY-MM-DD form); if the provisions do not answer the question, set answerable to "
        "false and say what is missing; do not give legal advice.",
        f"Question: {question}",
        f"Computed findings (authoritative):\n{json.dumps(findings, indent=1)}",
    ]
    if guidance:
        lessons = "\n".join(f"- {item}" for item in guidance)
        blocks.append(f"Verified regulatory reminders:\n{lessons}")
    if rejection_reason:
        blocks.append(
            f"IMPORTANT CORRECTION: Your previous draft was rejected because it "
            f"{rejection_reason}. Rewrite using ONLY exact citations listed below and ONLY "
            "ISO YYYY-MM-DD dates from the computed findings."
        )
    blocks.append(f"Provisions:\n{format_provisions(provisions)}")
    return "\n\n".join(blocks)


def format_provisions(provisions: tuple[Hit, ...]) -> str:
    """Provisions as the generator and judge see them: bracketed citation, headings, and text."""
    blocks = []
    for p in provisions:
        trail = " > ".join(h for h in p.headings if h)
        head = f"Headings: {trail}\n" if trail else ""
        blocks.append(f"[{p.citation}]\n{head}{p.body}")
    return "\n\n".join(blocks)


def _generate[T: BaseModel](
    generator: GenerativeModel, prompt: str, schema: type[T], thinking_level: ThinkingLevel | None
) -> T:
    return generator.generate(GenerationRequest(prompt, schema, thinking_level)).output
