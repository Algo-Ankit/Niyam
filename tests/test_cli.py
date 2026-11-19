from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import psycopg
import pytest

from niyam import cli
from niyam.evals import edge, end_to_end, retrieval
from niyam.retrieval import store


class _DummyContext:
    def __init__(self, events: list[str] | None = None, label: str = "") -> None:
        self._events = events
        self._label = label

    def __enter__(self) -> "_DummyContext":
        if self._events is not None:
            self._events.append(f"enter:{self._label}")
        return self

    def __exit__(self, *args: object) -> None:
        if self._events is not None:
            self._events.append(f"exit:{self._label}")

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


@dataclass
class _FakeCaseScore:
    passed: bool = True
    judge_failed: bool = False


@dataclass
class _FakeScenarioScore:
    id: str = "p1"


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
    events: list[str] = []

    def make_connect(label: str) -> Any:
        def fake_connect(*, autocommit: bool = False) -> _DummyContext:
            seen.append((label, autocommit))
            return _DummyContext(events, label)

        return fake_connect

    def fake_strict_answer(msg: str, as_of: object, svc: object) -> object:
        events.append("answer")
        return object()

    def fake_edge_eval(case: object, reply: object, judge: object) -> _FakeCaseScore:
        events.append("eval-edge:judge")
        return _FakeCaseScore()

    def fake_pipe_eval(sc: object, reply: object, judge: object) -> _FakeScenarioScore:
        events.append("eval-pipeline:judge")
        return _FakeScenarioScore()

    monkeypatch.setattr(cli, "get_settings", _FakeSettings)
    monkeypatch.setattr(cli, "build_models", lambda settings: _FakeModels())
    monkeypatch.setattr(cli, "_save", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "_strict_answer", fake_strict_answer)

    # _eval_edge opens per-case autocommit connections and closes before judging
    monkeypatch.setattr(cli, "_connect", make_connect("eval-edge"))
    monkeypatch.setattr(
        edge, "load_cases", lambda sets: [SimpleNamespace(id="c1", message="m", as_of="2026-11-19")]
    )
    monkeypatch.setattr(edge, "evaluate", fake_edge_eval)
    monkeypatch.setattr(edge, "summary", lambda scores: {"all": {"cases": 1}})
    assert cli._eval_edge(tmp_path / "edge.json", [tmp_path / "set.jsonl"]) == 0

    # _eval_pipeline opens per-case autocommit connections and closes before judging
    monkeypatch.setattr(cli, "_connect", make_connect("eval-pipeline"))
    monkeypatch.setattr(
        end_to_end,
        "load_scenarios",
        lambda path: [SimpleNamespace(id="p1", message="m", as_of="2026-11-19")],
    )
    monkeypatch.setattr(end_to_end, "evaluate", fake_pipe_eval)
    monkeypatch.setattr(end_to_end, "summary", lambda scores: {"scenarios": 1})
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
    assert events == [
        "enter:eval-edge",
        "answer",
        "exit:eval-edge",
        "eval-edge:judge",
        "enter:eval-pipeline",
        "answer",
        "exit:eval-pipeline",
        "eval-pipeline:judge",
        "enter:eval-retrieval",
        "exit:eval-retrieval",
        "enter:index",
        "exit:index",
    ]
