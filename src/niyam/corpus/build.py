"""Build the processed corpus file from downloaded sources."""

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from niyam.corpus import ecfr

F1_PARAGRAPH = (8, "214.2", "f")


def build_f1_corpus(source: Path, source_url: str, output: Path) -> int:
    """Parse 8 CFR 214.2(f) from `source` and write it to `output`; return the provision count."""
    root = ecfr.load(source)
    title, section, paragraph = F1_PARAGRAPH
    provisions = ecfr.parse_paragraph(root, title, section, paragraph)
    document = {
        "source_url": source_url,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "current_as_of": ecfr.current_as_of(root).isoformat(),
        "provisions": [asdict(p) for p in provisions],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(provisions)
