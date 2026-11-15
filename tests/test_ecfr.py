import xml.etree.ElementTree as ET
from datetime import date

import pytest

from niyam.corpus.ecfr import CfrParseError, current_as_of, parse_paragraph

# Mirrors govinfo eCFR markup: flat <P>s, italic level-5/6 labels, compound "(ii) Head-(A)".
_SECTION = """
<DLPSTEXTCLASS><AMDDATE>Oct. 14, 2026</AMDDATE>
<DIV8 N="§ 214.1" TYPE="SECTION"><P>(f) <I>Other section.</I> Not this one.</P></DIV8>
<DIV8 N="§ 214.2" TYPE="SECTION">
<P>(e) <I>Earlier.</I> Not parsed.</P>
<P>(f) <I>Students.</I> Intro text.</P>
<DIV><P>Table 2 to Paragraph (f)</P></DIV>
<P>(1) <I>Practical training.</I> See paragraph (f)(2) of this section.</P>
<P>(i) <I>Curricular practical training.</I> CPT text.</P>
<P>(ii) <I>Optional practical training</I>—(A) <I>General.</I> OPT text:</P>
<P>(<I>1</I>) During vacation;</P>
<P>(<I>2</I>) While in session.</P>
<P>Continuation of (A).</P>
<P>(B) <I>Termination.</I> Ends on transfer.</P>
<P>(2) <I>Process.</I> (i) <I>Student.</I> Student text.</P>
<P>(g) <I>Next paragraph.</I> Stop here.</P>
</DIV8></DLPSTEXTCLASS>
"""


def _root(xml: str = _SECTION) -> ET.Element:
    return ET.fromstring(xml)  # noqa: S314  # test fixture


def _by_citation() -> dict[str, tuple[tuple[str, ...], str]]:
    provisions = parse_paragraph(_root(), 8, "214.2", "f")
    return {p.citation: (p.headings, p.text) for p in provisions}


def test_recovers_hierarchy_from_flat_labels() -> None:
    assert list(_by_citation()) == [
        "8 CFR 214.2(f)",
        "8 CFR 214.2(f)(1)",
        "8 CFR 214.2(f)(1)(i)",
        "8 CFR 214.2(f)(1)(ii)",
        "8 CFR 214.2(f)(1)(ii)(A)",
        "8 CFR 214.2(f)(1)(ii)(A)(1)",
        "8 CFR 214.2(f)(1)(ii)(A)(2)",
        "8 CFR 214.2(f)(1)(ii)(B)",
        "8 CFR 214.2(f)(2)",
        "8 CFR 214.2(f)(2)(i)",
    ]


def test_splits_compound_paragraphs_and_keeps_headings() -> None:
    provisions = _by_citation()
    assert provisions["8 CFR 214.2(f)(1)(ii)"] == (
        ("Students", "Practical training", "Optional practical training"),
        "",
    )
    headings, text = provisions["8 CFR 214.2(f)(1)(ii)(A)"]
    assert headings[-1] == "General"
    assert text == "OPT text:"
    assert provisions["8 CFR 214.2(f)(2)(i)"][1] == "Student text."


def test_unlabelled_text_joins_the_open_provision_and_cross_references_stay_in_text() -> None:
    provisions = _by_citation()
    assert provisions["8 CFR 214.2(f)(1)(ii)(A)(2)"][1] == "While in session. Continuation of (A)."
    assert provisions["8 CFR 214.2(f)(1)"][1] == "See paragraph (f)(2) of this section."
    assert provisions["8 CFR 214.2(f)"][1] == "Intro text. Table 2 to Paragraph (f)"


def test_search_text_leads_with_citation_and_heading_path() -> None:
    provision = parse_paragraph(_root(), 8, "214.2", "f")[7]
    assert provision.search_text.startswith(
        "8 CFR 214.2(f)(1)(ii)(B) Students > Practical training > Optional practical training"
    )


def test_out_of_sequence_label_is_an_error() -> None:
    broken = _SECTION.replace("(<I>2</I>) While", "(<I>3</I>) While")
    with pytest.raises(CfrParseError, match=r"\(f\)\(1\)\(ii\)\(A\)\(1\): \(3\) does not follow"):
        parse_paragraph(_root(broken), 8, "214.2", "f")


def test_skipped_level_is_an_error() -> None:
    broken = _SECTION.replace("(i) <I>Curricular", "(A) <I>Curricular")
    with pytest.raises(CfrParseError, match="unexpected label"):
        parse_paragraph(_root(broken), 8, "214.2", "f")


def test_missing_section_or_paragraph_is_an_error() -> None:
    with pytest.raises(CfrParseError, match=r"section 214\.9"):
        parse_paragraph(_root(), 8, "214.9", "f")
    with pytest.raises(CfrParseError, match=r"paragraph \(c\)"):
        parse_paragraph(_root(), 8, "214.2", "c")


def test_paragraph_followed_by_a_roman_letter_is_refused() -> None:
    with pytest.raises(CfrParseError, match="successor"):
        parse_paragraph(_root(), 8, "214.2", "h")


def test_current_as_of_reads_the_amendment_date() -> None:
    assert current_as_of(_root()) == date(2026, 10, 14)
