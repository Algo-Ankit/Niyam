from datetime import date

from niyam.assistant.pipeline import Explanation, check_explanation, fact_dates
from niyam.retrieval.store import Hit
from niyam.rules.opt import StudentFacts, assess

_ASSESSMENT = assess(StudentFacts(program_end_date=date(2026, 5, 15)), date(2026, 5, 1))
_PROVISIONS = (Hit("8 CFR 214.2(f)(11)(i)(B)(2)", ("OPT",), "up to 90 days prior...", 0.0),)


def _explanation(text: str, citations: list[str]) -> Explanation:
    return Explanation(answerable=True, explanation=text, citations=citations)


def test_grounded_explanation_passes() -> None:
    text = "You can file from 2026-02-14 until 2026-06-14."
    assert (
        check_explanation(
            _explanation(text, ["8 CFR 214.2(f)(11)(i)(B)(2)"]), _ASSESSMENT, _PROVISIONS
        )
        is None
    )


def test_citation_not_given_to_the_model_is_rejected() -> None:
    reason = check_explanation(_explanation("ok", ["8 CFR 214.2(f)(12)"]), _ASSESSMENT, _PROVISIONS)
    assert reason is not None and "8 CFR 214.2(f)(12)" in reason


def test_date_the_rules_engine_did_not_compute_is_rejected() -> None:
    explanation = _explanation("File by 2026-07-14.", ["8 CFR 214.2(f)(11)(i)(B)(2)"])
    reason = check_explanation(explanation, _ASSESSMENT, _PROVISIONS)
    assert reason is not None and "2026-07-14" in reason


def test_dates_written_in_words_are_rejected_because_they_cannot_be_checked() -> None:
    for text in ("File by June 14.", "File by 6/14/2026."):
        reason = check_explanation(
            _explanation(text, ["8 CFR 214.2(f)(11)(i)(B)(2)"]), _ASSESSMENT, _PROVISIONS
        )
        assert reason is not None and "cannot be checked" in reason


def test_dates_the_student_gave_may_be_repeated() -> None:
    explanation = _explanation("Your program ended 2026-05-15.", ["8 CFR 214.2(f)(11)(i)(B)(2)"])
    given = fact_dates(StudentFacts(program_end_date=date(2026, 5, 15)))
    assert check_explanation(explanation, _ASSESSMENT, _PROVISIONS, given) is None
    assert check_explanation(explanation, _ASSESSMENT, _PROVISIONS) is not None


def test_literal_dates_from_retrieved_provisions_are_allowed_but_altered_years_rejected() -> None:
    provisions = (
        Hit(
            "8 CFR 214.2(f)(5)(ii)(C)",
            (),
            "Applies to students admitted on or after September 15, 2026, extended until April 1.",
            0.0,
        ),
    )
    cite = ["8 CFR 214.2(f)(5)(ii)(C)"]
    for ok_text in (
        "This applies starting September 15, 2026 and runs until April 1.",
        "This applies starting 2026-09-15. After day 10 may come another step.",
        "You get a separate 30-day departure period and a decision 15 days later.",
    ):
        assert check_explanation(_explanation(ok_text, cite), _ASSESSMENT, provisions) is None
    for bad_text in (
        "This applies starting September 15, 2027.",
        "This runs until April 1, 2029.",
        "This runs until April 1 2029.",
        "This runs until April 1st, 2029.",
        "File by june 14, 2027.",
        "File by 15 September 2027.",
        "This applies starting 2027-09-15.",
    ):
        assert check_explanation(_explanation(bad_text, cite), _ASSESSMENT, provisions) is not None
