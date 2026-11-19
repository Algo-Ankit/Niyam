"""OPT, STEM OPT and H-1B cap-gap rules, from 8 CFR 214.2(f) (current 2026-10-14).

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
    "not_yet_open",
    "open",
    "closed",
    "upcoming",
    "passed",
    "within_limit",
    "over_limit",
    "not_applicable",
    "ended",
]
PetitionOutcome = Literal["pending", "approved", "rejected", "denied", "revoked", "withdrawn"]
_TERMINATING: frozenset[PetitionOutcome] = frozenset({"rejected", "denied", "revoked", "withdrawn"})

_CFR = "8 CFR 214.2(f)"
_STEM_MIN_HOURS = 20  # (f)(10)(ii)(C)(8): "not ... less than 20 hours per week"
_BUSINESS_DAYS = (
    "Business days exclude weekends and US federal holidays (not defined in the paragraph)."
)


class Job(BaseModel):
    employer: str = Field(default="", description="Employer name, if given")
    start: date = Field(description="First day of this job")
    end: date | None = Field(default=None, description="Last day of this job; null if ongoing")
    related_to_major: bool | None = Field(
        default=None,
        description="Whether the student says this job is directly related to their major; "
        "null if they did not say",
    )
    hours_per_week: int | None = Field(
        default=None, description="Hours worked per week, if the student said"
    )


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
    jobs: list[Job] | None = Field(
        default=None,
        description="Jobs held during OPT; [] only if the student explicitly says they had no "
        "jobs; null if the student did not mention employment history",
    )
    h1b_petition_filed: bool | None = Field(
        default=None,
        description="True if the student says an employer filed a cap-subject H-1B petition for "
        "them; null if not mentioned",
    )
    h1b_change_of_status: bool | None = Field(
        default=None,
        description="True if that petition requests a change of status, False if it is for "
        "consular processing; null if not said",
    )
    h1b_fiscal_year: int | None = Field(
        default=None,
        description="Fiscal year of the requested H-1B status (FY 2027 starts 2026-10-01)",
    )
    h1b_petition_outcome: PetitionOutcome | None = Field(
        default=None, description="Current state of the H-1B petition, if the student said"
    )
    h1b_validity_start: date | None = Field(
        default=None, description="Validity start date of the approved H-1B petition"
    )
    h1b_outcome_date: date | None = Field(
        default=None,
        description="Date the H-1B petition was rejected, denied, revoked or withdrawn",
    )


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
    missing.extend(_date_contradictions(facts))
    missing.extend(_unconfirmed_job_facts(facts))
    missing.extend(_unconfirmed_cap_gap_facts(facts))
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
    if facts.jobs is None or _opt_dates_inverted(facts):
        return
    start = _known(facts.opt_start_date)
    stem = bool(facts.on_stem_extension)
    limit = 150 if stem else 90
    authorized_end = (
        _stem_end(facts) if (stem and facts.opt_end_date is not None) else facts.opt_end_date
    )
    last_day = min(as_of, authorized_end) if authorized_end else as_of
    stem_start = _stem_start(facts)
    used = _days_without_a_job(start, last_day, facts.jobs, as_of, stem_start)
    status: Status = "over_limit" if used > limit else "within_limit"
    assumptions = [
        "Counting starts on the OPT EAD start date (SEVP practice; the regulation is silent).",
        *_job_assumptions(facts.jobs, stem_start),
    ]
    if stem and facts.opt_end_date is None:
        assumptions.append(
            "Initial OPT end date was not given, so the STEM OPT 20-hour minimum could not be "
            "checked by date."
        )
    yield Finding(
        "unemployment_days",
        f"{_CFR}(10)(ii)(E)",
        f"{used} of {limit} allowed days of unemployment used, {max(limit - used, 0)} left",
        status,
        assumptions=tuple(assumptions),
    )


def _job_assumptions(jobs: list[Job], stem_start: date | None) -> Iterable[str]:
    """How each job was counted, where the student did not say what the rule needs."""
    for job in jobs:
        name = job.employer or f"the job starting {job.start}"
        if job.related_to_major is False:
            yield f"{name} is not related to the major, so its days count as unemployment."
        elif job.related_to_major is None:
            yield (
                f"{name} is taken to be directly related to the major ((f)(10)(ii)(A)); "
                "if it is not, its days count as unemployment."
            )
        if _in_stem_period(job, stem_start) and job.hours_per_week is None:
            yield (
                f"{name} is taken to be at least {_STEM_MIN_HOURS} hours a week during STEM OPT "
                "((f)(10)(ii)(C)(8)); fewer hours would not count as employment."
            )


def _stem_filing_window(facts: StudentFacts, as_of: date) -> Iterable[Finding]:
    if not facts.stem_degree or facts.on_stem_extension or _opt_dates_inverted(facts):
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
    if not facts.on_stem_extension or _opt_dates_inverted(facts):
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
        if report_date > end:  # reporting ends when the extension concludes
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


def _stem_job_reports(facts: StudentFacts, as_of: date) -> Iterable[Finding]:
    if not facts.on_stem_extension or not facts.jobs or _opt_dates_inverted(facts):
        return
    start: date | None
    end: date | None
    if facts.opt_end_date is not None:
        start, end = facts.opt_end_date + timedelta(days=1), _stem_end(facts)
        extra_assumptions: tuple[str, ...] = ()
    else:
        start = end = None
        extra_assumptions = ("Assumes this job change occurred during your STEM OPT extension.",)
    for job in facts.jobs:
        name = job.employer or "a job"
        if start is None or (end is not None and start <= job.start <= end):
            due = job.start + timedelta(days=10)
            yield Finding(
                "stem_new_employer_i983",
                f"{_CFR}(10)(ii)(C)(7)(iv)",
                f"New Form I-983 for {name} (started {job.start}) is due to the DSO by {due}",
                _deadline(due, as_of),
                closes=due,
                assumptions=("Applies when the job is with a new employer.", *extra_assumptions),
            )
        if job.end is not None and (start is None or (end is not None and start <= job.end <= end)):
            due = job.end + timedelta(days=10)
            yield Finding(
                "stem_report_loss_of_employment",
                f"{_CFR}(12)(ii)(A)",
                f"Report the end of {name} ({job.end}) to the DSO by {due}",
                _deadline(due, as_of),
                closes=due,
                assumptions=extra_assumptions,
            )


def _departure_period(facts: StudentFacts, as_of: date) -> Iterable[Finding]:
    if _cap_gap_handles_departure(facts) or _opt_dates_inverted(facts):
        return  # cap-gap sets the departure/extension end date, or OPT dates contradict
    if facts.opt_end_date is not None:
        authorized_end = _stem_end(facts) if facts.on_stem_extension else facts.opt_end_date
        last = authorized_end + timedelta(days=30)
        yield Finding(
            "departure_period",
            f"{_CFR}(5)(v)",
            f"After OPT ends on {authorized_end}, the 30-day period to depart or change status "
            f"ends on {last}",
            _deadline(last, as_of),
            closes=last,
            assumptions=("Assumes no further OPT or change of status is pending.",),
        )
    elif (
        facts.program_end_date is not None
        and facts.opt_start_date is None
        and not facts.on_stem_extension
    ):
        last = facts.program_end_date + timedelta(days=30)
        yield Finding(
            "departure_period",
            f"{_CFR}(5)(v)",
            f"After your program ends, the 30-day period to depart or change status ends on {last}",
            _deadline(last, as_of),
            closes=last,
            assumptions=("Applies if you do not apply for OPT, transfer, or change status.",),
        )


def _cap_gap(facts: StudentFacts, as_of: date) -> Iterable[Finding]:
    """The H-1B cap-gap extension of F-1 status and OPT, 8 CFR 214.2(f)(5)(vii)."""
    if not facts.h1b_petition_filed:
        return
    if facts.h1b_change_of_status is False:
        yield Finding(
            "cap_gap_extension",
            f"{_CFR}(5)(vii)(A)",
            "No cap-gap extension: it applies only to a petition requesting a change of status, "
            "not consular processing",
            "not_applicable",
        )
        return
    if facts.h1b_fiscal_year is None or not _valid_fiscal_year(facts.h1b_fiscal_year):
        return
    if facts.h1b_petition_outcome in _TERMINATING:
        yield Finding(
            "cap_gap_extension",
            f"{_CFR}(5)(vii)(B)",
            f"The cap-gap extension ended when the petition was {facts.h1b_petition_outcome}",
            "ended",
        )
        yield from _cap_gap_departure(facts, as_of)
        return
    april_first = date(facts.h1b_fiscal_year, 4, 1)
    end = april_first
    if facts.h1b_petition_outcome == "approved" and facts.h1b_validity_start is not None:
        end = min(april_first, facts.h1b_validity_start)
    assumptions = [
        "The petition is cap-subject, timely filed and nonfrivolous ((f)(5)(vii)(A)).",
        "You have not violated your F-1 status ((f)(5)(vii)(C)).",
        "Work authorisation extends only if your OPT or STEM OPT was valid; otherwise only "
        "status is extended.",
    ]
    if facts.h1b_petition_outcome is None:
        assumptions.append("The petition is taken to be pending.")
    yield Finding(
        "cap_gap_extension",
        f"{_CFR}(5)(vii)(A)",
        f"F-1 status and OPT work authorisation are extended until {end} (April 1 of fiscal "
        f"year {facts.h1b_fiscal_year}, or the approved petition's start date if earlier)",
        _deadline(end, as_of),
        closes=end,
        assumptions=tuple(assumptions),
    )


# NOTE: (f)(5)(vii) does not say how long a student has to depart after a terminated cap-gap
# extension. SEVP's page (2025-04-10) says 60 days from the later of termination and the OPT end,
# but predates the 2026 rule that cut (f)(5)(v) to 30 days; we give the cautious 30-day date.
def _cap_gap_departure(facts: StudentFacts, as_of: date) -> Iterable[Finding]:
    if facts.h1b_outcome_date is None or _opt_dates_inverted(facts):
        return
    ends = [facts.h1b_outcome_date]
    if facts.opt_end_date is not None:
        ends.append(_stem_end(facts) if facts.on_stem_extension else facts.opt_end_date)
    last = max(ends) + timedelta(days=30)
    yield Finding(
        "cap_gap_departure",
        f"{_CFR}(5)(v)",
        f"Plan to depart or change status by {last} (30 days after the later of the petition "
        "decision and your OPT end date)",
        _deadline(last, as_of),
        closes=last,
        assumptions=(
            "The regulation does not state the departure period after a cap-gap extension "
            "ends. This is the cautious reading of the 30-day period in (f)(5)(v); SEVP's "
            "2025 guidance says 60 days but predates the 2026 rule. Confirm with your DSO.",
        ),
    )


def _cap_gap_handles_departure(facts: StudentFacts) -> bool:
    """True when cap-gap (active or terminated) supersedes the ordinary post-OPT departure rule."""
    return bool(
        facts.h1b_petition_filed
        and facts.h1b_change_of_status is not False
        and facts.h1b_fiscal_year is not None
        and _valid_fiscal_year(facts.h1b_fiscal_year)
    )


def _valid_fiscal_year(year: int) -> bool:
    return 2000 <= year <= 2100


def _opt_dates_inverted(facts: StudentFacts) -> bool:
    return (
        facts.opt_start_date is not None
        and facts.opt_end_date is not None
        and facts.opt_end_date < facts.opt_start_date
    )


def _date_contradictions(facts: StudentFacts) -> Iterable[str]:
    if _opt_dates_inverted(facts):
        yield "confirm your OPT start and end dates (end date is earlier than start date)"
    if facts.h1b_fiscal_year is not None and not _valid_fiscal_year(facts.h1b_fiscal_year):
        yield "confirm the 4-digit H-1B fiscal year"


_Rule = Callable[[StudentFacts, date], Iterable[Finding]]
_RULES: tuple[tuple[tuple[str, ...], _Rule], ...] = (
    (("program_end_date",), _opt_filing_window),
    (("program_end_date",), _opt_start_limit),
    (("program_end_date",), _opt_completion_limit),
    (("opt_start_date",), _unemployment),
    (("opt_end_date", "stem_degree"), _stem_filing_window),
    (("opt_end_date",), _stem_obligations),
    ((), _stem_job_reports),
    ((), _departure_period),
    ((), _cap_gap),
)


def _stem_start(facts: StudentFacts) -> date | None:
    if facts.on_stem_extension and facts.opt_end_date is not None:
        return facts.opt_end_date + timedelta(days=1)
    return None


def _stem_end(facts: StudentFacts) -> date:
    start = _known(facts.opt_end_date) + timedelta(days=1)
    return add_months(start, 24) - timedelta(days=1)


def _days_without_a_job(
    first: date, last: date, jobs: list[Job], as_of: date, stem_start: date | None
) -> int:
    """Days from `first` to `last` not covered by qualifying employment.

    A job does not qualify if the student says it is unrelated to the major, and during a STEM
    extension (from `stem_start`) if it is under 20 hours a week. Unknown facts count as
    qualifying; `_job_assumptions` says so and `_unconfirmed_job_facts` asks for them.
    """
    employed: set[date] = set()
    for job in jobs:
        if job.related_to_major is False:
            continue
        part_time = job.hours_per_week is not None and job.hours_per_week < _STEM_MIN_HOURS
        day, job_last = max(job.start, first), min(job.end or as_of, last)
        while day <= job_last:
            if not (part_time and stem_start is not None and day >= stem_start):
                employed.add(day)
            day += timedelta(days=1)
    total = (last - first).days + 1
    return max(total, 0) - len(employed)


def _unconfirmed_job_facts(facts: StudentFacts) -> Iterable[str]:
    """Job facts needed for unemployment counting or assumed on listed jobs."""
    if facts.jobs is None:
        if facts.opt_start_date is not None and not _opt_dates_inverted(facts):
            yield "your OPT jobs (or whether you have been unemployed)"
        return
    if any(job.related_to_major is None for job in facts.jobs):
        yield "whether each job is directly related to your major"
    stem_start = _stem_start(facts)
    if any(_in_stem_period(j, stem_start) and j.hours_per_week is None for j in facts.jobs):
        yield "hours per week of each job during STEM OPT"


def _unconfirmed_cap_gap_facts(facts: StudentFacts) -> Iterable[str]:
    """Cap-gap facts to ask for, only once the student says an H-1B petition was filed."""
    if not facts.h1b_petition_filed:
        return
    if facts.h1b_change_of_status is None:
        yield "h1b_change_of_status"
    if facts.h1b_fiscal_year is None:
        yield "h1b_fiscal_year"
    if facts.h1b_petition_outcome in _TERMINATING and facts.h1b_outcome_date is None:
        yield "h1b_outcome_date"
    if facts.h1b_petition_outcome == "approved" and facts.h1b_validity_start is None:
        yield "h1b_validity_start"


def _in_stem_period(job: Job, stem_start: date | None) -> bool:
    return stem_start is not None and (job.end is None or job.end >= stem_start)


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
