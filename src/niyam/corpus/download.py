"""Download official source files once, politely, and record each in a manifest."""

import gzip
import hashlib
import json
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

USER_AGENT = "niyam-corpus/0.1 (educational RAG project)"
ECFR_TITLE_8 = "https://www.govinfo.gov/bulkdata/ECFR/title-8/ECFR-title8.xml"
_TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class SourceRecord:
    url: str
    path: str
    sha256: str
    size_bytes: int
    last_modified: str | None
    fetched_at: str


def fetch(url: str, destination: Path) -> SourceRecord:
    """Download `url` to `destination` with a clearly named client; HTTP errors propagate."""
    if not url.startswith("https://"):
        raise ValueError(f"only https sources are allowed: {url}")
    request = urllib.request.Request(  # noqa: S310  # scheme checked above
        url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"}
    )
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310
        body = response.read()
        if response.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        last_modified = response.headers.get("Last-Modified")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(body)
    return SourceRecord(
        url=url,
        path=destination.as_posix(),
        sha256=hashlib.sha256(body).hexdigest(),
        size_bytes=len(body),
        last_modified=last_modified,
        fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )


def record(manifest: Path, entry: SourceRecord) -> None:
    """Add or replace `entry` (keyed by URL) in the JSON manifest."""
    entries = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else []
    entries = [e for e in entries if e["url"] != entry.url] + [asdict(entry)]
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
