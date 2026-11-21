"""Tests for Langfuse online evaluation & failure harvesting (D76)."""

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from pydantic import BaseModel

from niyam.evals import online
from niyam.evals.judge import JUDGE_ATTEMPTS
from niyam.evals.online import (
    EvaluatedTrace,
    LiveTrace,
    OnlineEvalConfig,
    OnlineVerdict,
    classify_failure,
    format_cited_provisions,
    load_corpus_map,
    run_online_eval,
)
from niyam.models.errors import ProviderResponseError
from niyam.models.types import GenerationRequest, GenerationResult, Usage

_ROOT = Path(__file__).parents[1]
_NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)


def _trace(**overrides: object) -> LiveTrace:
    base: dict[str, object] = {
        "trace_id": "trace_00000001",
        "started_at": _NOW,
        "level": "DEFAULT",
        "status_message": None,
        "question": "When can I file for OPT?",
        "as_of": "2026-11-21",
        "kind": "question",
        "withheld": False,
        "withheld_reason": None,
        "rerank_failed": False,
        "findings": 1,
        "findings_summaries": ("File Form I-765 (8 CFR 214.2(f)(11)(i)(B)(2))",),
        "out_of_scope": (),
        "cited_provisions": ("8 CFR 214.2(f)(11)(i)(B)(2)",),
        "explanation": "File within the filing window.",
        "user_feedback": None,
        "user_feedback_comment": None,
        "online_grounded": None,
        "online_grounded_reason": None,
    }
    return LiveTrace(**(base | overrides))  # type: ignore[arg-type]


class _FakeOnlineStore:
    def __init__(self, traces: list[LiveTrace]) -> None:
        self.traces = traces
        self.since_seen: datetime | None = None
        self.datasets: list[tuple[str, str]] = []
        self.recorded: list[EvaluatedTrace] = []
        self.harvested: list[tuple[str, EvaluatedTrace]] = []
        self.flushes = 0

    def fetch_traces(self, since: datetime, max_traces: int) -> list[LiveTrace]:
        self.since_seen = since
        return self.traces[:max_traces]

    def ensure_dataset(self, name: str, description: str) -> None:
        self.datasets.append((name, description))

    def record_scores(self, item: EvaluatedTrace) -> None:
        self.recorded.append(item)

    def harvest_failure(self, dataset_name: str, item: EvaluatedTrace) -> None:
        self.harvested.append((dataset_name, item))

    def flush(self) -> None:
        self.flushes += 1


class _FakeJudge:
    model_id = "fake-judge"

    def __init__(self, grounded: bool = True, malformed: int = 0) -> None:
        self.prompts: list[str] = []
        self._grounded = grounded
        self._malformed = malformed

    def generate[T: BaseModel](self, request: GenerationRequest[T]) -> GenerationResult[T]:
        self.prompts.append(request.prompt)
        if len(self.prompts) <= self._malformed:
            raise ProviderResponseError("malformed JSON")
        verdict = OnlineVerdict(
            grounded=self._grounded,
            reason="Grounded in cited rule." if self._grounded else "Unsupported claim.",
        )
        return GenerationResult(request.schema.model_validate(verdict.model_dump()), Usage())


def test_classify_failure_prioritizes_reliability_guards_rerank_feedback_grounding() -> None:
    assert classify_failure(_trace(level="ERROR", withheld=True)) == ("stage_error", "reliability")
    assert classify_failure(
        _trace(withheld=True, withheld_reason="stated dates the rules engine did not compute")
    ) == ("withheld_date", "guardrail_or_prompt")
    assert classify_failure(
        _trace(withheld=True, withheld_reason="cited provisions it was not given: ['x']")
    ) == ("withheld_citation", "guardrail_or_prompt")
    assert classify_failure(_trace(withheld=True, withheld_reason="other")) == (
        "withheld_other",
        "guardrail_or_prompt",
    )
    assert classify_failure(_trace(rerank_failed=True, user_feedback=False)) == (
        "rerank_failed",
        "retrieval_rerank",
    )
    assert classify_failure(_trace(user_feedback=False, online_grounded=False)) == (
        "negative_feedback",
        "user_reported",
    )
    assert classify_failure(_trace(online_grounded=False)) == (
        "ungrounded",
        "generation_grounding",
    )
    assert classify_failure(_trace(online_grounded=True, user_feedback=True)) == ("none", "none")


def test_corpus_map_and_formatting_include_parent_headings() -> None:
    corpus = load_corpus_map(_ROOT / "data/processed/8-cfr-214.2-f.json")
    assert len(corpus) >= 180
    formatted = format_cited_provisions(["8 CFR 214.2(f)(12)(ii)(A)", "missing-cite"], corpus)
    assert "24-month OPT extension" in formatted
    assert "[missing-cite]\n(not found in indexed corpus)" in formatted


def test_online_eval_respects_budget_skips_scored_and_harvests_failures(tmp_path: Path) -> None:
    corpus = load_corpus_map(_ROOT / "data/processed/8-cfr-214.2-f.json")
    traces = [
        _trace(trace_id="already_scored", online_grounded=True),
        _trace(trace_id="greeting_trace", kind="greeting", cited_provisions=(), findings=0),
        _trace(trace_id="withheld_trace", withheld=True, withheld_reason="stated dates..."),
        _trace(trace_id="unscored_1"),
        _trace(trace_id="unscored_2"),
    ]
    store = _FakeOnlineStore(traces)
    judge = _FakeJudge(grounded=False)
    out = tmp_path / "failures.jsonl"

    summary = run_online_eval(
        store,
        judge,
        corpus,
        config=OnlineEvalConfig(hours=24, max_traces=50, max_judge=1, out_path=out),
        now=_NOW,
    )

    assert len(judge.prompts) == 1
    assert "unscored_1" not in judge.prompts[0]
    assert "Headings:" in judge.prompts[0]
    assert summary.traces_fetched == 5
    assert summary.newly_judged == 1
    assert summary.judge_failed == 0
    assert summary.failures_harvested == 2  # withheld_trace + unscored_1 (ungrounded)
    assert summary.counts_by_type == {"none": 3, "withheld_date": 1, "ungrounded": 1}
    assert len(store.datasets) == 1
    assert len(store.recorded) == 5
    assert [item.trace.trace_id for _, item in store.harvested] == ["withheld_trace", "unscored_1"]
    assert store.flushes == 1

    lines = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [row["trace_id"] for row in lines] == ["withheld_trace", "unscored_1"]


def test_dry_run_skips_mutations_and_handles_judge_failures(tmp_path: Path) -> None:
    corpus = load_corpus_map(_ROOT / "data/processed/8-cfr-214.2-f.json")
    store = _FakeOnlineStore(
        [_trace(trace_id="bad_judge_trace"), _trace(trace_id="err", level="ERROR")]
    )
    judge = _FakeJudge(malformed=JUDGE_ATTEMPTS)
    out = tmp_path / "dry.jsonl"

    summary = run_online_eval(
        store,
        judge,
        corpus,
        config=OnlineEvalConfig(dry_run=True, out_path=out),
        now=_NOW,
    )

    assert len(judge.prompts) == JUDGE_ATTEMPTS
    assert summary.judge_failed == 1
    assert summary.newly_judged == 0
    assert summary.failures_harvested == 1
    assert (
        store.datasets == []
        and store.recorded == []
        and store.harvested == []
        and store.flushes == 0
    )
    assert len(out.read_text(encoding="utf-8").splitlines()) == 1


def test_observation_parser_handles_json_strings_and_score_v3_variants() -> None:
    obs = SimpleNamespace(
        trace_id="t12345678",
        start_time=_NOW,
        level="DEFAULT",
        status_message=None,
        input=json.dumps({"question": "What is cap-gap?", "as_of": "2026-11-21"}),
        output=json.dumps(
            {
                "kind": "question",
                "withheld": False,
                "rerank_failed": False,
                "findings": 1,
                "cited_provisions": ["8 CFR 214.2(f)(5)(vii)(A)"],
                "findings_summaries": ["Cap-gap summary"],
                "out_of_scope": [],
                "explanation": "It extends status.",
            }
        ),
    )
    scores = [
        SimpleNamespace(name="user_feedback", value=False, comment="missing dates"),
        SimpleNamespace(name="online_grounded", value=True, comment="supported"),
    ]
    parsed = online._observation_to_trace(obs, scores)
    assert parsed.question == "What is cap-gap?"
    assert parsed.user_feedback is False and parsed.user_feedback_comment == "missing dates"
    assert parsed.online_grounded is True and parsed.online_grounded_reason == "supported"
    assert parsed.cited_provisions == ("8 CFR 214.2(f)(5)(vii)(A)",)
