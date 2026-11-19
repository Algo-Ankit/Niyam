from pathlib import Path
from types import SimpleNamespace
from typing import Any

import psycopg
import pytest

from niyam import cli
from niyam.evals import edge, end_to_end, retrieval
from niyam.retrieval import store


class _DummyContext:
    def __enter__(self) -> "_DummyContext":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def close(self) -> None:
        return None


class _FakeModels(_DummyContext):
    def __init__(self) -> None:
        self.generator = object()
        self.decision = object()
        self.judge = object()
        self.embedder = SimpleNamespace(dimensions=768)


class _FakeSettings:
    def __init__(self) -> None:
        self.database_url = SimpleNamespace(get_secret_value=lambda: "postgresql://example/db")
        self.generation_thinking_level = "low"
        self.generation_model = "gen"
        self.decision_model = "dec"
        self.judge_model = "judge"
        self.embedding_model = "emb"


def test_connect_forwards_autocommit(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_connect(dsn: str, **kwargs: Any) -> object:
        calls.append({"dsn": dsn, **kwargs})
        return object()

    monkeypatch.setattr(cli, "get_settings", _FakeSettings)
    monkeypatch.setattr(psycopg, "connect", fake_connect)

    cli._connect()
    cli._connect(autocommit=True)

    assert calls == [
        {"dsn": "postgresql://example/db", "connect_timeout": 20, "autocommit": False},
        {"dsn": "postgresql://example/db", "connect_timeout": 20, "autocommit": True},
    ]


def test_eval_commands_open_autocommit_connections(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: list[tuple[str, bool]] = []

    def make_connect(label: str) -> Any:
        def fake_connect(*, autocommit: bool = False) -> _DummyContext:
            seen.append((label, autocommit))
            return _DummyContext()

        return fake_connect

    monkeypatch.setattr(cli, "get_settings", _FakeSettings)
    monkeypatch.setattr(cli, "build_models", lambda settings: _FakeModels())
    monkeypatch.setattr(cli, "_save", lambda *args, **kwargs: None)

    # _eval_edge
    monkeypatch.setattr(cli, "_connect", make_connect("eval-edge"))
    monkeypatch.setattr(edge, "load_cases", lambda sets: [])
    monkeypatch.setattr(edge, "summary", lambda scores: {"all": {"cases": 0}})
    assert cli._eval_edge(tmp_path / "edge.json", [tmp_path / "set.jsonl"]) == 0

    # _eval_pipeline
    monkeypatch.setattr(cli, "_connect", make_connect("eval-pipeline"))
    monkeypatch.setattr(end_to_end, "load_scenarios", lambda path: [])
    monkeypatch.setattr(end_to_end, "summary", lambda scores: {"scenarios": 0})
    assert cli._eval_pipeline(tmp_path / "pipeline.json") == 0

    # _eval_retrieval
    monkeypatch.setattr(cli, "_connect", make_connect("eval-retrieval"))
    monkeypatch.setattr(retrieval, "load_items", lambda path: [])
    monkeypatch.setattr(retrieval, "run", lambda *args: [])
    monkeypatch.setattr(retrieval, "metrics", lambda ranked: {})
    monkeypatch.setattr(retrieval, "comparisons", lambda ranked: {})
    assert (
        cli._eval_retrieval(tmp_path / "ret.json", tmp_path / "r.jsonl", hyde=False, rerank=False)
        == 0
    )

    # _index keeps default transactional mode (autocommit=False)
    monkeypatch.setattr(cli, "_connect", make_connect("index"))
    monkeypatch.setattr(store, "create_schema", lambda conn, dims: None)
    monkeypatch.setattr(store, "load_corpus", lambda conn, path, emb: 0)
    assert cli._index() == 0

    assert seen == [
        ("eval-edge", True),
        ("eval-pipeline", True),
        ("eval-retrieval", True),
        ("index", False),
    ]
