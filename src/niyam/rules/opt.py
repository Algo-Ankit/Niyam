"""OPT and STEM OPT deadlines and unemployment limits, from 8 CFR 214.2(f) (current 2026-10-14).

Every number here is quoted from the regulation text in data/processed; each Finding cites the
paragraph it comes from. Calendar days unless the regulation says business days.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from niyam.rules.dates import add_business_days, add_months

Status = Literal[
    "not_yet_open", "open", "closed", "upcoming", "passed", "within_limit", "over_limit"
]

_CFR = "8 CFR 214.2(f)"
_BUSINESS_DAYS = (
    "Business days exclude weekends and US federal holidays (not defined in the paragraph)."
)


class Job(BaseModel):
    employer: str = Field(default="", description="Employer name, if given")
    start: date = Field(description="First day of this job")
    end: date | None = Field(default=None, description="Last day of this job; null if ongoing")


class StudentFacts(BaseModel):
    """What the student told us. Unknown facts stay null; rules that need them are skipped."""

    program_end_date: date | None = Field(
        default=None, description="Program end date on the Form I-20"
    )
    opt_recommendation_date: date | None = Field(
        default=None,
        description="Date the DSO entered the post-completion OPT recommendation in SEVIS",
    )
    opt_start_date: date | None = Field(
        default=None, description="Start date on the post-completion OPT EAD (Form I-766)"
    )
    opt_end_date: date | None = Field(
        default=None, description="End date on the post-completion OPT EAD (Form I-766)"
    )
    stem_degree: bool | None = Field(
        default=None, description="Whether the degree is on the STEM Designated Degree Program List"
    )
    stem_recommendation_date: date | None = Field(
        default=None, description="Date the DSO entered the STEM OPT extension recommendation"
    )
    on_stem_extension: bool | None = Field(
        default=None, description="Whether a 24-month STEM OPT extension has been approved"
    )
    jobs: list[Job] = Field(default_factory=list, description="Jobs held during OPT")


@dataclass(frozen=True)
class Finding:
    rule: str
    citation: str
    summary: str
    status: Status
    opens: date | None = None
    closes: date | None = None
    assumptions: tuple[str, ...] = ()


@dataclass(frozen=True)
class Assessment:
    findings: tuple[Finding, ...]
    missing: tuple[str, ...]  # StudentFacts fields that would unlock more rules


def assess(facts: StudentFacts, as_of: date) -> Assessment:
    """Every rule that the known facts allow, evaluated on `as_of`."""
    findings: list[Finding] = []
    missing: list[str] = []
    for needs, rule in _RULES:
        absent = [name for name in needs if getattr(facts, name) is None]
        if absent:
            missing.extend(n for n in absent if n not in missing)
        else:
            findings.extend(rule(facts, as_of))
    return Assessment(tuple(findings), tuple(missing))


def _opt_filing_window(facts: StudentFacts, as_of: date) -> Iterable[Finding]:
    end = _known(facts.program_end_date)
    opens, closes = end - timedelta(days=90), end + timedelta(days=30)
    summary = f"File Form I-765 for post-completion OPT from {opens} to {closes}"
    if facts.opt_recommendation_date is not None:
        closes = min(closes, facts.opt_recommendation_date + timedelta(days=30))
        summary = (
            f"File Form I-765 for post-completion OPT from {opens} to {closes} (no later than "
            "30 days after the program end date and within 30 days of the DSO recommendation)"
        )
    yield Finding(
        "opt_filing_window",
        f"{_CFR}(11)(i)(B)(2)",
        summary,
        _window(opens, closes, as_of),
        opens,
        closes,
    )


def _opt_start_limit(facts: StudentFacts, as_of: date) -> Iterable[Finding]:
    latest = _known(facts.program_end_date) + timedelta(days=30)
    yield Finding(
        "opt_latest_start_date",
        f"{_CFR}(11)(i)(D)",
        f"The requested OPT start date can be no later than {latest}",
        _deadline(latest, as_of),
        closes=latest,
    )


def _opt_completion_limit(facts: StudentFacts, as_of: date) -> Iterable[Finding]:
    latest = add_months(_known(facts.program_end_date), 14)
    yield Finding(
        "opt_completion_limit",
        f"{_CFR}(10)(ii)(A)(3)",
        f"All post-completion OPT must be completed by {latest} (a STEM extension is exempt)",
        _deadline(latest, as_of),
        closes=latest,
        assumptions=("Completion of study is taken to be the program end date.",),
    )


def _unemployment(facts: StudentFacts, as_of: date) -> Iterable[Finding]:
    start = _known(facts.opt_start_date)
    stem = bool(facts.on_stem_extension)
    limit = 150 if stem else 90
    authorized_end = _stem_end(facts) if stem else facts.opt_end_date
    last_day = min(as_of, authorized_end) if authorized_end else as_of
    used = _days_without_a_job(start, last_day, facts.jobs, as_of)
    status: Status = "over_limit" if used > limit else "within_limit"
    yield Finding(
        "unemployment_days",
        f"{_CFR}(10)(ii)(E)",
        f"{used} of {limit} allowed days of unemployment used, {max(limit - used, 0)} left",
        status,
        assumptions=(
            "Counting starts on the OPT EAD start date (SEVP practice; the regulation is silent).",
            "Every job listed is treated as qualifying OPT employment.",
        ),
    )


def _stem_filing_window(facts: StudentFacts, as_of: date) -> Iterable[Finding]:
    if not facts.stem_degree or facts.on_stem_extension:
        return
    expiry = _known(facts.opt_end_date)
    opens, closes = expiry - timedelta(days=90), expiry
    summary = f"File Form I-765 for the 24-month STEM OPT extension from {opens} to {closes}"
    if facts.stem_recommendation_date is not None:
        closes = min(closes, facts.stem_recommendation_date + timedelta(days=60))
        summary += f", and within 60 days of the DSO recommendation (by {closes})"
    yield Finding(
        "stem_filing_window",
        f"{_CFR}(11)(i)(C)",
        summary,
        _window(opens, closes, as_of),
        opens,
        closes,
        assumptions=("The extension must be filed while the current OPT EAD is still valid.",),
    )


def _stem_obligations(facts: StudentFacts, as_of: date) -> Iterable[Finding]:
    if not facts.on_stem_extension:
        return
    start = _known(facts.opt_end_date) + timedelta(days=1)
    end = _stem_end(facts)
    yield Finding(
        "stem_period",
        f"{_CFR}(11)(iii)(A)",
        f"The STEM OPT extension runs from {start} to {end}",
        _window(start, end, as_of),
        start,
        end,
        assumptions=("'Ends 24 months thereafter' is taken as the day before the 24-month date.",),
    )
    for number in range(1, 5):
        report_date = add_months(start, 6 * number)
        if report_date > end + timedelta(days=1):
            break
        due = add_business_days(report_date, 10)
        yield Finding(
            f"stem_validation_report_{number}",
            f"{_CFR}(12)(ii)(B)",
            f"Validation report {number} (reporting date {report_date}) is due to the DSO by {due}",
            _deadline(due, as_of),
            closes=due,
            assumptions=(_BUSINESS_DAYS,),
        )
    evaluation_due = add_months(start, 12) + timedelta(days=10)
    yield Finding(
        "stem_12_month_evaluation",
        f"{_CFR}(10)(ii)(C)(9)(i)",
        f"The 12-month self-evaluation (Form I-983) is due to the DSO by {evaluation_due}",
        _deadline(evaluation_due, as_of),
        closes=evaluation_due,
    )
    for job in facts.jobs:
        name = job.employer or "a job"
        if start <= job.start <= end:
            due = job.start + timedelta(days=10)
            yield Finding(
                "stem_new_employer_i983",
                f"{_CFR}(10)(ii)(C)(7)(iv)",
                f"New Form I-983 for {name} (started {job.start}) is due to the DSO by {due}",
                _deadline(due, as_of),
                closes=due,
                assumptions=("Applies when the job is with a new employer.",),
            )
        if job.end is not None and start <= job.end <= end:
            due = job.end + timedelta(days=10)
            yield Finding(
                "stem_report_loss_of_employment",
                f"{_CFR}(12)(ii)(A)",
                f"Report the end of {name} ({job.end}) to the DSO by {due}",
                _deadline(due, as_of),
                closes=due,
            )


def _departure_period(facts: StudentFacts, as_of: date) -> Iterable[Finding]:
    authorized_end = _stem_end(facts) if facts.on_stem_extension else _known(facts.opt_end_date)
    last = authorized_end + timedelta(days=30)
    yield Finding(
        "departure_period",
        f"{_CFR}(5)(v)",
        f"After OPT ends on {authorized_end}, the 30-day period to depart or change status ends "
        f"on {last}",
        _deadline(last, as_of),
        closes=last,
        assumptions=("Assumes no further OPT or change of status is pending.",),
    )


_Rule = Callable[[StudentFacts, date], Iterable[Finding]]
_RULES: tuple[tuple[tuple[str, ...], _Rule], ...] = (
    (("program_end_date",), _opt_filing_window),
    (("program_end_date",), _opt_start_limit),
    (("program_end_date",), _opt_completion_limit),
    (("opt_start_date",), _unemployment),
    (("opt_end_date", "stem_degree"), _stem_filing_window),
    (("opt_end_date",), _stem_obligations),
    (("opt_end_date",), _departure_period),
)


def _stem_end(facts: StudentFacts) -> date:
    start = _known(facts.opt_end_date) + timedelta(days=1)
    return add_months(start, 24) - timedelta(days=1)


def _days_without_a_job(first: date, last: date, jobs: list[Job], as_of: date) -> int:
    employed: set[date] = set()
    for job in jobs:
        day, job_last = max(job.start, first), min(job.end or as_of, last)
        while day <= job_last:
            employed.add(day)
            day += timedelta(days=1)
    total = (last - first).days + 1
    return max(total, 0) - len(employed)


def _window(opens: date, closes: date, as_of: date) -> Status:
    if as_of < opens:
        return "not_yet_open"
    return "open" if as_of <= closes else "closed"


def _deadline(due: date, as_of: date) -> Status:
    return "upcoming" if as_of <= due else "passed"


def _known(value: date | None) -> date:
    if value is None:
        raise ValueError("rule called without a required fact")  # assess() checks first
    return value
