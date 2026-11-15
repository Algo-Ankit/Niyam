import gzip
import json
import urllib.request
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from unittest.mock import patch

import pytest

from niyam.corpus import download
from niyam.corpus.download import SourceRecord, fetch, record

_BODY = b"<xml>title 8</xml>"


class _Handler(BaseHTTPRequestHandler):
    seen_agents: list[str] = []  # noqa: RUF012  # class-level capture for the test server

    def do_GET(self) -> None:
        _Handler.seen_agents.append(self.headers.get("User-Agent", ""))
        payload = gzip.compress(_BODY)
        self.send_response(200)
        self.send_header("Content-Encoding", "gzip")
        self.send_header("Last-Modified", "Thu, 15 Oct 2026 21:57:00 GMT")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture
def server_url() -> Iterator[str]:
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/title-8.xml"
    server.shutdown()


def test_fetch_decompresses_names_the_client_and_hashes(server_url: str, tmp_path: Path) -> None:
    https_url = server_url.replace("http://", "https://")
    real_request = urllib.request.Request

    def plain_http(url: str, headers: dict[str, str]) -> object:
        return real_request(url.replace("https://", "http://"), headers=headers)

    with patch.object(urllib.request, "Request", plain_http):
        entry = fetch(https_url, tmp_path / "raw" / "t8.xml")

    assert (tmp_path / "raw" / "t8.xml").read_bytes() == _BODY
    assert entry.size_bytes == len(_BODY)
    assert entry.last_modified == "Thu, 15 Oct 2026 21:57:00 GMT"
    assert len(entry.sha256) == 64
    assert _Handler.seen_agents[-1] == download.USER_AGENT


def test_fetch_refuses_non_https(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="only https"):
        fetch("http://example.org/x.xml", tmp_path / "x.xml")


def test_record_replaces_the_entry_for_the_same_url(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    old = SourceRecord("https://a", "p", "1" * 64, 1, None, "2026-11-01T00:00:00+00:00")
    other = SourceRecord("https://b", "q", "2" * 64, 2, None, "2026-11-01T00:00:00+00:00")
    new = SourceRecord("https://a", "p", "3" * 64, 3, None, "2026-11-15T00:00:00+00:00")
    for entry in (old, other, new):
        record(manifest, entry)
    entries = json.loads(manifest.read_text(encoding="utf-8"))
    assert [(e["url"], e["size_bytes"]) for e in entries] == [("https://b", 2), ("https://a", 3)]
