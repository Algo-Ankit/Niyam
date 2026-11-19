"""Expected dates are worked by hand from the numbers in 8 CFR 214.2(f), not from the code."""

import json
from datetime import date
from pathlib import Path

from niyam.rules.dates import add_business_days, add_months, federal_holidays, is_business_day
from niyam.rules.opt import Finding, Job, StudentFacts, assess

_CORPUS = Path(__file__).parents[1] / "data" / "processed" / "8-cfr-214.2-f.json"


def _by_rule(facts: StudentFacts, as_of: date) -> dict[str, Finding]:
    return {f.rule: f for f in assess(facts, as_of).findings}


def test_add_months_clamps_to_month_end() -> None:
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2028, 2, 29), 12) == date(2029, 2, 28)
    assert add_months(date(2026, 5, 15), 14) == date(2027, 7, 15)


def test_federal_holidays_move_to_the_observed_weekday() -> None:
    assert date(2026, 7, 3) in federal_holidays(2026)  # July 4, 2026 is a Saturday
    assert date(2027, 6, 18) in federal_holidays(2027)  # Juneteenth 2027 is a Saturday
    assert date(2026, 11, 26) in federal_holidays(2026)  # Thanksgiving
    assert add_business_days(date(2026, 11, 25), 1) == date(2026, 11, 27)


def test_year_boundary_observed_new_years_day_is_not_a_business_day() -> None:
    # Jan 1, 2028 is a Saturday, so its observed holiday is Friday Dec 31, 2027.
    assert is_business_day(date(2027, 12, 31)) is False
    assert add_business_days(date(2027, 12, 20), 10) == date(2028, 1, 5)


def test_post_completion_filing_window_is_90_days_before_to_30_days_after_program_end() -> None:
    rules = _by_rule(StudentFacts(program_end_date=date(2026, 5, 15)), date(2026, 5, 1))
    window = rules["opt_filing_window"]
    assert (window.opens, window.closes, window.status) == (
        date(2026, 2, 14),
        date(2026, 6, 14),
        "open",
    )
    assert window.citation == "8 CFR 214.2(f)(11)(i)(B)(2)"
    assert rules["opt_latest_start_date"].closes == date(2026, 6, 14)
    assert rules["opt_completion_limit"].closes == date(2027, 7, 15)


def test_dso_recommendation_shortens_the_filing_window_to_30_days() -> None:
    facts = StudentFacts(
        program_end_date=date(2026, 5, 15), opt_recommendation_date=date(2026, 5, 1)
    )
    window = _by_rule(facts, date(2026, 6, 3))["opt_filing_window"]
    assert (window.closes, window.status) == (date(2026, 5, 31), "closed")


def test_unemployment_counts_days_without_a_job_since_the_ead_start() -> None:
    facts = StudentFacts(
        opt_start_date=date(2026, 6, 1),
        opt_end_date=date(2027, 5, 31),
        jobs=[Job(employer="Acme", start=date(2026, 6, 1), end=date(2026, 8, 10))],
    )
    finding = _by_rule(facts, date(2026, 9, 8))["unemployment_days"]
    assert finding.summary.startswith("29 of 90 allowed days of unemployment used, 61 left")
    assert finding.status == "within_limit"


def test_unemployment_over_the_limit() -> None:
    facts = StudentFacts(opt_start_date=date(2026, 6, 1), opt_end_date=date(2027, 5, 31), jobs=[])
    finding = _by_rule(facts, date(2026, 9, 1))["unemployment_days"]
    assert finding.status == "over_limit"
    assert finding.summary.startswith("93 of 90 allowed days")


def test_stem_extension_raises_the_unemployment_limit_to_150() -> None:
    facts = StudentFacts(
        opt_start_date=date(2026, 6, 1),
        opt_end_date=date(2027, 5, 31),
        on_stem_extension=True,
        jobs=[],
    )
    finding = _by_rule(facts, date(2026, 9, 1))["unemployment_days"]
    assert (finding.status, finding.summary[:22]) == ("within_limit", "93 of 150 allowed days")


def test_unmentioned_jobs_ask_instead_of_claiming_over_limit() -> None:
    facts = StudentFacts(opt_start_date=date(2026, 6, 1), opt_end_date=date(2027, 5, 31))
    assessment = assess(facts, date(2027, 2, 1))
    assert "unemployment_days" not in {f.rule for f in assessment.findings}
    assert "your OPT jobs (or whether you have been unemployed)" in assessment.missing


def test_stem_extension_without_opt_end_date_does_not_crash_and_reports_job_deadlines() -> None:
    facts = StudentFacts(
        opt_start_date=date(2026, 6, 1),
        on_stem_extension=True,
        jobs=[Job(employer="Acme", start=date(2028, 2, 25), end=date(2028, 3, 1))],
    )
    rules = _by_rule(facts, date(2028, 3, 2))
    assert rules["stem_new_employer_i983"].closes == date(2028, 3, 6)
    assert rules["stem_report_loss_of_employment"].closes == date(2028, 3, 11)
    assert "unemployment_days" in rules


def test_inverted_opt_dates_are_flagged_instead_of_computing_bogus_findings() -> None:
    facts = StudentFacts(
        opt_start_date=date(2027, 6, 1),
        opt_end_date=date(2026, 12, 1),
        stem_degree=True,
        on_stem_extension=True,
        jobs=[Job(start=date(2027, 6, 1))],
    )
    assessment = assess(facts, date(2027, 7, 1))
    assert assessment.findings == ()
    assert any("end date is earlier than start date" in m for m in assessment.missing)


def test_departure_period_after_program_end_when_not_on_opt() -> None:
    rules = _by_rule(StudentFacts(program_end_date=date(2026, 12, 18)), date(2026, 12, 20))
    assert rules["departure_period"].closes == date(2027, 1, 17)
    stem = _by_rule(
        StudentFacts(program_end_date=date(2026, 12, 18), on_stem_extension=True),
        date(2027, 5, 1),
    )
    assert "departure_period" not in stem


def test_out_of_range_h1b_fiscal_year_does_not_crash() -> None:
    for bad_fy in (0, 27, 10000):
        facts = _cap_gap_student(h1b_change_of_status=True, h1b_fiscal_year=bad_fy)
        assessment = assess(facts, date(2026, 7, 15))
        assert "cap_gap_extension" not in {f.rule for f in assessment.findings}
        assert "confirm the 4-digit H-1B fiscal year" in assessment.missing


def test_stem_filing_window_and_60_day_recommendation_limit() -> None:
    facts = StudentFacts(
        opt_end_date=date(2027, 5, 31),
        stem_degree=True,
        stem_recommendation_date=date(2027, 3, 15),
    )
    window = _by_rule(facts, date(2027, 3, 20))["stem_filing_window"]
    assert (window.opens, window.closes, window.status) == (
        date(2027, 3, 2),
        date(2027, 5, 14),
        "open",
    )


def test_no_stem_window_without_a_stem_degree() -> None:
    facts = StudentFacts(opt_end_date=date(2027, 5, 31), stem_degree=False)
    assert "stem_filing_window" not in _by_rule(facts, date(2027, 3, 20))


def test_stem_period_reports_and_evaluation() -> None:
    facts = StudentFacts(
        opt_end_date=date(2027, 5, 31),
        on_stem_extension=True,
        jobs=[Job(employer="Beta", start=date(2027, 9, 1), end=date(2028, 1, 31))],
    )
    rules = _by_rule(facts, date(2027, 10, 1))
    assert (rules["stem_period"].opens, rules["stem_period"].closes) == (
        date(2027, 6, 1),
        date(2029, 5, 31),
    )
    assert rules["stem_validation_report_1"].closes == date(2027, 12, 15)
    assert "stem_validation_report_3" in rules
    # The 24-month date (2029-06-01) falls after the period ends, so (f)(12)(ii)(B) needs no 4th.
    assert "stem_validation_report_4" not in rules
    assert rules["stem_12_month_evaluation"].closes == date(2028, 6, 11)
    assert rules["stem_new_employer_i983"].closes == date(2027, 9, 11)
    assert rules["stem_report_loss_of_employment"].closes == date(2028, 2, 10)
    assert rules["departure_period"].closes == date(2029, 6, 30)


def test_departure_period_is_30_days_after_opt_ends() -> None:
    rules = _by_rule(StudentFacts(opt_end_date=date(2027, 5, 31)), date(2027, 6, 10))
    assert rules["departure_period"].closes == date(2027, 6, 30)


def test_missing_facts_are_reported_instead_of_guessed() -> None:
    assessment = assess(StudentFacts(), date(2026, 5, 1))
    assert assessment.findings == ()
    assert assessment.missing == (
        "program_end_date",
        "opt_start_date",
        "opt_end_date",
        "stem_degree",
    )


def test_every_cited_paragraph_exists_in_the_corpus() -> None:
    corpus = json.loads(_CORPUS.read_text(encoding="utf-8"))
    citations = {p["citation"] for p in corpus["provisions"]}
    facts = StudentFacts(
        program_end_date=date(2026, 5, 15),
        opt_recommendation_date=date(2026, 5, 1),
        opt_start_date=date(2026, 6, 1),
        opt_end_date=date(2027, 5, 31),
        stem_degree=True,
        on_stem_extension=True,
        jobs=[Job(start=date(2027, 9, 1), end=date(2028, 1, 31))],
    )
    before_stem = facts.model_copy(update={"on_stem_extension": False})
    cited = {
        f.citation
        for scenario in (
            facts,
            before_stem,
            _cap_gap_student(h1b_change_of_status=True, h1b_fiscal_year=2027),
            _cap_gap_student(
                h1b_change_of_status=True,
                h1b_fiscal_year=2027,
                h1b_petition_outcome="denied",
                h1b_outcome_date=date(2026, 8, 1),
            ),
        )
        for f in assess(scenario, date(2027, 10, 1)).findings
    }
    assert len(cited) == 13, sorted(cited)  # every rule's paragraph is exercised
    assert cited <= citations, cited - citations


def test_a_job_unrelated_to_the_major_counts_as_unemployment() -> None:
    facts = StudentFacts(
        opt_start_date=date(2026, 6, 1),
        opt_end_date=date(2027, 5, 31),
        jobs=[
            Job(
                employer="Cafe",
                start=date(2026, 6, 1),
                end=date(2026, 8, 10),
                related_to_major=False,
            )
        ],
    )
    finding = _by_rule(facts, date(2026, 9, 8))["unemployment_days"]
    assert finding.summary.startswith("100 of 90 allowed days")
    assert finding.status == "over_limit"
    assert "Cafe is not related to the major" in " ".join(finding.assumptions)


def test_under_20_hours_does_not_count_during_stem_but_does_before_it() -> None:
    part_time = Job(start=date(2027, 5, 1), end=None, related_to_major=True, hours_per_week=15)
    facts = StudentFacts(
        opt_start_date=date(2026, 6, 1),
        opt_end_date=date(2027, 5, 31),
        on_stem_extension=True,
        jobs=[Job(start=date(2026, 6, 1), end=date(2027, 4, 30), related_to_major=True), part_time],
    )
    # May 2027 is covered (no hours minimum on regular OPT); June 1 to 10 under STEM is not.
    finding = _by_rule(facts, date(2027, 6, 10))["unemployment_days"]
    assert finding.summary.startswith("10 of 150 allowed days")


def test_unknown_job_facts_are_assumed_visibly_and_asked_for() -> None:
    facts = StudentFacts(
        opt_start_date=date(2026, 6, 1),
        opt_end_date=date(2027, 5, 31),
        on_stem_extension=True,
        jobs=[Job(employer="Acme", start=date(2026, 6, 1), end=None)],
    )
    assessment = assess(facts, date(2027, 7, 1))
    unemployment = next(f for f in assessment.findings if f.rule == "unemployment_days")
    assert unemployment.summary.startswith("0 of 150")
    joined = " ".join(unemployment.assumptions)
    assert "Acme is taken to be directly related to the major" in joined
    assert "Acme is taken to be at least 20 hours a week" in joined
    assert "whether each job is directly related to your major" in assessment.missing
    assert "hours per week of each job during STEM OPT" in assessment.missing


def test_confirmed_jobs_need_no_questions() -> None:
    facts = StudentFacts(
        opt_start_date=date(2026, 6, 1),
        jobs=[Job(start=date(2026, 6, 1), end=None, related_to_major=True)],
    )
    assert assess(facts, date(2026, 7, 1)).missing == (
        "program_end_date",
        "opt_end_date",
        "stem_degree",
    )


def _cap_gap_student(**h1b: object) -> StudentFacts:
    student = StudentFacts(
        opt_start_date=date(2025, 7, 1),
        opt_end_date=date(2026, 6, 30),
        jobs=[Job(start=date(2025, 7, 1), end=None, related_to_major=True)],
        h1b_petition_filed=True,
    )
    return StudentFacts.model_validate(student.model_dump() | h1b)


def test_pending_cap_gap_extends_status_to_april_1_and_replaces_the_departure_period() -> None:
    facts = _cap_gap_student(h1b_change_of_status=True, h1b_fiscal_year=2027)
    rules = _by_rule(facts, date(2026, 7, 15))
    gap = rules["cap_gap_extension"]
    assert (gap.citation, gap.closes, gap.status) == (
        "8 CFR 214.2(f)(5)(vii)(A)",
        date(2027, 4, 1),
        "upcoming",
    )
    assert "The petition is taken to be pending." in gap.assumptions
    assert "departure_period" not in rules


def test_approved_petition_ends_cap_gap_at_its_start_date_if_earlier() -> None:
    facts = _cap_gap_student(
        h1b_change_of_status=True,
        h1b_fiscal_year=2027,
        h1b_petition_outcome="approved",
        h1b_validity_start=date(2026, 10, 1),
    )
    assert _by_rule(facts, date(2026, 7, 15))["cap_gap_extension"].closes == date(2026, 10, 1)


def test_consular_processing_gets_no_cap_gap_and_keeps_the_departure_period() -> None:
    facts = _cap_gap_student(h1b_change_of_status=False, h1b_fiscal_year=2027)
    rules = _by_rule(facts, date(2026, 7, 15))
    assert rules["cap_gap_extension"].status == "not_applicable"
    assert rules["departure_period"].closes == date(2026, 7, 30)


def test_denied_petition_ends_cap_gap_with_the_cautious_departure_date() -> None:
    facts = _cap_gap_student(
        h1b_change_of_status=True,
        h1b_fiscal_year=2027,
        h1b_petition_outcome="denied",
        h1b_outcome_date=date(2026, 8, 1),
    )
    rules = _by_rule(facts, date(2026, 8, 5))
    assert (rules["cap_gap_extension"].status, rules["cap_gap_extension"].citation) == (
        "ended",
        "8 CFR 214.2(f)(5)(vii)(B)",
    )
    departure = rules["cap_gap_departure"]
    assert departure.closes == date(2026, 8, 31)  # later of 2026-08-01 and 2026-06-30, + 30
    assert "SEVP's 2025 guidance says 60 days" in departure.assumptions[0]
    assert "departure_period" not in rules


def test_cap_gap_questions_are_asked_only_after_a_petition_is_mentioned() -> None:
    asked = assess(_cap_gap_student(), date(2026, 7, 15)).missing
    assert ("h1b_change_of_status" in asked, "h1b_fiscal_year" in asked) == (True, True)
    plain = StudentFacts(opt_start_date=date(2025, 7, 1))
    assert not [m for m in assess(plain, date(2026, 7, 15)).missing if m.startswith("h1b")]
    denied = _cap_gap_student(
        h1b_change_of_status=True, h1b_fiscal_year=2027, h1b_petition_outcome="withdrawn"
    )
    assert "h1b_outcome_date" in assess(denied, date(2026, 8, 5)).missing
