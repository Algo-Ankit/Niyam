"""Live provider verification: one minimal real call per provider, cache bypassed.

Each check is independent, so one failing provider does not hide the state of the others.
Error messages are truncated and never include settings values.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass

import psycopg
from langfuse import Langfuse
from langfuse.api import AccessDeniedError, UnauthorizedError
from pydantic import BaseModel

from niyam.config import Settings
from niyam.models.factory import ModelSuite
from niyam.models.types import EmbeddingInput, GenerationRequest

MAX_ERROR_CHARS = 200

_PASSAGE = (
    "Full-KYC PPIs: the amount outstanding shall not exceed Rs 2,00,000 at any point of time."
)


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    ok: bool
    detail: str
    seconds: float


class _Probe(BaseModel):
    answer: str
    abstain: bool


def run_checks(settings: Settings, models: ModelSuite) -> list[CheckResult]:
    checks: list[tuple[str, Callable[[], str]]] = [
        ("decision", lambda: _check_decision(models)),
        ("generation", lambda: _check_generation(settings, models)),
        ("judge", lambda: _check_judge(models)),
        ("embedding", lambda: _check_embedding(models)),
        ("database", lambda: _check_database(settings)),
        ("langfuse", lambda: _check_langfuse(settings)),
    ]
    return [_timed(name, check) for name, check in checks]


def _timed(name: str, check: Callable[[], str]) -> CheckResult:
    start = time.perf_counter()
    try:
        detail = check()
    except Exception as error:  # report every provider failure, then keep checking the rest
        message = f"{type(error).__name__}: {error}"[:MAX_ERROR_CHARS]
        return CheckResult(name, False, message, time.perf_counter() - start)
    return CheckResult(name, True, detail, time.perf_counter() - start)


def _check_decision(models: ModelSuite) -> str:
    state = f"Question: What is the balance limit of a full-KYC PPI?\nPassage: {_PASSAGE}"
    result = models.decision.decide(
        state,
        {
            "relevant": "Does the passage help answer the question?",
            "about_tax": "Is the passage about income tax?",
        },
    )
    p = result.probabilities
    if not (p["relevant"] > 0.5 > p["about_tax"]):
        raise AssertionError(f"implausible probabilities {p}")
    return f"{models.decision.model_id} P(relevant)={p['relevant']:.2f} P(tax)={p['about_tax']:.2f}"


_PROBE_PROMPT = (
    "Answer only from the passage. If it does not answer the question, set abstain to true."
    f"\n\nPassage: {_PASSAGE}\n\n<question>What is the limit for a full-KYC PPI?</question>"
)


def _check_generation(settings: Settings, models: ModelSuite) -> str:
    result = models.generator.generate(
        GenerationRequest(_PROBE_PROMPT, _Probe, settings.generation_thinking_level)
    )
    if result.output.abstain or "2,00,000" not in result.output.answer:
        raise AssertionError(f"unexpected answer {result.output.answer[:80]!r}")
    return f"{models.generator.model_id} ok, {result.usage.total_tokens} tokens"


def _check_judge(models: ModelSuite) -> str:
    result = models.judge.generate(GenerationRequest(_PROBE_PROMPT, _Probe, None))
    if result.output.abstain or "2,00,000" not in result.output.answer:
        raise AssertionError(f"unexpected answer {result.output.answer[:80]!r}")
    return f"{models.judge.model_id} ok, {result.usage.total_tokens} tokens"


def _check_embedding(models: ModelSuite) -> str:
    result = models.embedder.embed(
        [
            EmbeddingInput(_PASSAGE, "document", "PPI Master Direction"),
            EmbeddingInput("full-KYC PPI balance limit", "query"),
        ]
    )
    return (
        f"{models.embedder.model_id} {len(result.vectors)} vectors x {models.embedder.dimensions}"
    )


def _check_database(settings: Settings) -> str:
    with psycopg.connect(settings.database_url.get_secret_value(), connect_timeout=20) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        row = conn.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()
        if row is None:
            raise AssertionError("pgvector extension is not installed")
        hit = conn.execute(
            "SELECT to_tsvector('english', %s) @@ websearch_to_tsquery('english', %s)",
            ("Cash withdrawal is not permitted", "cash withdrawal"),
        ).fetchone()
        if hit is None or hit[0] is not True:
            raise AssertionError("English full-text search did not match")
        server = conn.info.server_version
    return f"Postgres {server // 10000}, pgvector {row[0]}, English full-text search ok"


def _check_langfuse(settings: Settings) -> str:
    client = Langfuse(
        public_key=settings.langfuse_public_key.get_secret_value(),
        secret_key=settings.langfuse_secret_key.get_secret_value(),
        host=settings.langfuse_host,
    )
    try:
        if not client.auth_check():
            raise AssertionError("credentials rejected")
    except (UnauthorizedError, AccessDeniedError) as error:
        # The SDK's own message starts with a header dump; say what to check instead.
        raise AssertionError(
            "credentials rejected: check that LANGFUSE_PUBLIC_KEY starts with pk-lf-, "
            "LANGFUSE_SECRET_KEY with sk-lf-, and LANGFUSE_HOST matches the project's region"
        ) from error
    finally:
        client.shutdown()
    return f"authenticated against {settings.langfuse_host}"
