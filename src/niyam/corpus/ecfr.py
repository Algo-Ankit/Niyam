"""Parse one top-level paragraph of a CFR section from govinfo's bulk eCFR XML.

eCFR XML gives every paragraph as a flat <P> whose text starts with its label, such as "(10)".
The hierarchy is recovered from the label style, which the CFR fixes by level: (a) letter,
(1) digit, (i) roman, (A) capital, then italic (1) digit and italic (i) roman.
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

_I_OPEN, _I_CLOSE = "\x01", "\x02"
_LABEL = re.compile(
    rf"^\s*\((?:{_I_OPEN}(?P<italic>[0-9a-z]+){_I_CLOSE}|(?P<plain>[0-9A-Za-z]+))\)\s*"
)
_HEADING = re.compile(rf"^{_I_OPEN}(?P<heading>[^{_I_CLOSE}]+){_I_CLOSE}")
_DASH = re.compile(r"^\s*[\u2014\u2013-]?\s*")  # em dash, en dash or hyphen
_MARKERS = re.compile(f"[{_I_OPEN}{_I_CLOSE}]")
_ROMANS = [
    "i",
    "ii",
    "iii",
    "iv",
    "v",
    "vi",
    "vii",
    "viii",
    "ix",
    "x",
    "xi",
    "xii",
    "xiii",
    "xiv",
    "xv",
    "xvi",
    "xvii",
    "xviii",
    "xix",
    "xx",
    "xxi",
    "xxii",
    "xxiii",
    "xxiv",
    "xxv",
    "xxvi",
    "xxvii",
    "xxviii",
    "xxix",
    "xxx",
]
_LETTER, _DIGIT, _ROMAN, _CAPITAL, _ITALIC_DIGIT, _ITALIC_ROMAN = range(1, 7)


class CfrParseError(ValueError):
    """The XML does not follow the CFR paragraph structure this parser relies on."""


@dataclass(frozen=True)
class Provision:
    """One labelled paragraph, such as 8 CFR 214.2(f)(10)(ii)(E), with its own text only."""

    citation: str
    labels: tuple[str, ...]
    headings: tuple[str, ...]
    text: str

    @property
    def search_text(self) -> str:
        """Text to index: the citation and heading path first, so context is searchable."""
        path = " > ".join(h for h in self.headings if h)
        return f"{self.citation} {path}\n{self.text}".strip()


@dataclass
class _Draft:
    labels: tuple[str, ...]
    headings: tuple[str, ...]
    level: int
    ordinal: int
    parts: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Label:
    text: str
    level: int
    ordinal: int


def load(path: Path) -> ET.Element:
    """Parse a govinfo eCFR XML file."""
    # NOTE: stdlib ElementTree with expat >= 2.4.1 (bundled with Python 3.12) resolves no
    # external entities and limits entity expansion; the input is a government bulk file.
    return ET.parse(path).getroot()  # noqa: S314


def current_as_of(root: ET.Element) -> date:
    """The date the eCFR title is current to (its AMDDATE element, e.g. "Oct. 14, 2026")."""
    element = root.find(".//AMDDATE")
    if element is None or not element.text:
        raise CfrParseError("no AMDDATE element")
    return datetime.strptime(element.text.strip(), "%b. %d, %Y").date()


def parse_paragraph(root: ET.Element, title: int, section: str, paragraph: str) -> list[Provision]:
    """Return every provision of `section` paragraph `paragraph`, in document order.

    Raises CfrParseError if a label breaks the CFR numbering sequence, so a silent
    mis-nesting can never reach the index.
    """
    successor = chr(ord(paragraph) + 1)
    if successor in _ROMANS:
        # NOTE: "(h)" is followed by "(i)", which is also a roman level-3 label; not supported.
        raise CfrParseError(f"paragraph ({paragraph}) cannot be delimited by its successor")
    drafts: list[_Draft] = []
    for element in _section(root, section):
        marked = _marked_text(element)
        if not drafts:
            first = _leading_label(marked) if element.tag == "P" else None
            if first is not None and first[0].level == _LETTER and first[0].text == paragraph:
                drafts.extend(_open_provisions(marked, [], title, section))
            continue
        found = _leading_label(marked) if element.tag == "P" else None
        if found is not None and found[0].level == _LETTER:
            break
        if found is None:
            drafts[-1].parts.append(_clean(marked))
        else:
            drafts.extend(_open_provisions(marked, drafts, title, section))
    if not drafts:
        raise CfrParseError(f"paragraph ({paragraph}) not found in section {section}")
    return [_freeze(d, title, section) for d in drafts]


def _section(root: ET.Element, section: str) -> list[ET.Element]:
    for div in root.iter("DIV8"):
        if div.get("N", "").split()[-1:] == [section]:
            return list(div)
    raise CfrParseError(f"section {section} not found")


def _open_provisions(
    marked: str, open_drafts: list[_Draft], title: int, section: str
) -> list[_Draft]:
    """Start the provision(s) a labelled <P> opens: one, or two for "(ii) Heading-(A) text"."""
    stack = _path_of(open_drafts)
    created: list[_Draft] = []
    rest = marked
    while (found := _leading_label(rest)) is not None:
        label, end = found
        rest = rest[end:]
        parent = _attach(stack, label, title, section)
        heading_match = _HEADING.match(rest)
        heading = heading_match.group("heading").strip().rstrip(".") if heading_match else ""
        if heading_match:
            rest = rest[heading_match.end() :]
        draft = _Draft(
            labels=(*parent.labels, label.text) if parent else (label.text,),
            headings=(*parent.headings, heading) if parent else (heading,),
            level=label.level,
            ordinal=label.ordinal,
        )
        stack.append(draft)
        created.append(draft)
        child = _leading_label(_DASH.sub("", rest, count=1))
        if not heading or child is None or not _starts_level(child[0], label.level + 1):
            break
        rest = _DASH.sub("", rest, count=1)
    created[-1].parts.append(_clean(rest))
    return created


def _path_of(drafts: list[_Draft]) -> list[_Draft]:
    """The chain of open ancestors ending at the most recent provision."""
    path: list[_Draft] = []
    for draft in drafts:
        while path and path[-1].level >= draft.level:
            path.pop()
        path.append(draft)
    return path


def _attach(stack: list[_Draft], label: _Label, title: int, section: str) -> _Draft | None:
    """Pop `stack` to the new label's parent and check the numbering; return the parent."""
    if not stack:
        if label.level != _LETTER:
            raise CfrParseError(
                f"{title} CFR {section}: first label ({label.text}) is not a letter"
            )
        return None
    while stack and stack[-1].level > label.level:
        stack.pop()
    top = stack[-1] if stack else None
    if top is not None and top.level == label.level:
        if label.ordinal != top.ordinal + 1:
            raise CfrParseError(
                f"{_citation(title, section, top.labels)}: ({label.text}) does not follow"
            )
        stack.pop()
        return stack[-1] if stack else None
    if top is None or label.level != top.level + 1 or label.ordinal != 1:
        where = _citation(title, section, top.labels) if top else f"{title} CFR {section}"
        raise CfrParseError(f"{where}: unexpected label ({label.text})")
    return top


def _starts_level(label: _Label, level: int) -> bool:
    return label.level == level and label.ordinal == 1


def _leading_label(marked: str) -> tuple[_Label, int] | None:
    """The label at the start of `marked` and where it ends, or None."""
    match = _LABEL.match(marked)
    if match is None:
        return None
    label = _classify(match.group("italic"), match.group("plain"))
    return None if label is None else (label, match.end())


def _classify(italic: str | None, plain: str | None) -> _Label | None:
    """Level and ordinal of a label, from its style; None if it is not a CFR label."""
    text = italic if italic is not None else plain
    if text is None:
        return None
    level, ordinal = None, 0
    if text.isdigit():
        level, ordinal = (_ITALIC_DIGIT if italic else _DIGIT), int(text)
    elif text in _ROMANS:
        level, ordinal = (_ITALIC_ROMAN if italic else _ROMAN), _ROMANS.index(text) + 1
    elif italic is None and len(text) == 1:
        lower = text.islower()
        level, ordinal = (_LETTER if lower else _CAPITAL), ord(text.lower()) - ord("a") + 1
    return None if level is None else _Label(text, level, ordinal)


def _marked_text(element: ET.Element) -> str:
    """Element text with <I> content wrapped in marker characters; other markup flattened."""
    parts = [element.text or ""]
    for child in element:
        inner = "".join(child.itertext())
        parts.append(f"{_I_OPEN}{inner}{_I_CLOSE}" if child.tag == "I" else inner)
        parts.append(child.tail or "")
    return "".join(parts)


def _clean(marked: str) -> str:
    return " ".join(_MARKERS.sub("", marked).split())


def _citation(title: int, section: str, labels: tuple[str, ...]) -> str:
    return f"{title} CFR {section}" + "".join(f"({label})" for label in labels)


def _freeze(draft: _Draft, title: int, section: str) -> Provision:
    return Provision(
        citation=_citation(title, section, draft.labels),
        labels=draft.labels,
        headings=draft.headings,
        text=" ".join(p for p in draft.parts if p),
    )
