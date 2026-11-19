"""Command-line entry point: `uv run niyam <command>`."""

import argparse
import json
import subprocess
import sys
import time
from contextlib import closing
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path

import psycopg

from niyam.assistant import pipeline
from niyam.config import get_settings
from niyam.corpus import build, download
from niyam.evals import answers as answers_eval
from niyam.evals import edge as edge_eval
from niyam.evals import end_to_end
from niyam.evals import extraction as extraction_eval
from niyam.evals import retrieval as retrieval_eval
from niyam.models.factory import build_models
from niyam.models.interfaces import DecisionModel
from niyam.retrieval import hyde as hyde_search
from niyam.retrieval import rerank, store
from niyam.verify import run_checks

RAW_TITLE_8 = Path("data/raw/ECFR-title8.xml")
MANIFEST = Path("data/manifest.json")
F1_CORPUS = Path("data/processed/8-cfr-214.2-f.json")
RETRIEVAL_DEV_SET = Path("evals/retrieval-dev.jsonl")
RETRIEVAL_TEST_SET = Path("evals/retrieval-test.jsonl")
PIPELINE_SET = Path("evals/pipeline.jsonl")
EXTRACTION_SET = Path("evals/extraction.jsonl")
EDGE_SETS = (
    Path("evals/independent/edge_cases.jsonl"),
    Path("evals/independent/decline_and_security.jsonl"),
)


def _verify_providers() -> int:
    settings = get_settings()
    models = build_models(settings, use_cache=False)
    try:
        results = run_checks(settings, models)
        ledger_rows = models.ledger.summary()
    finally:
        models.close()

    for r in results:
        print(f"{'PASS' if r.ok else 'FAIL'}  {r.name:<10} {r.seconds:6.1f}s  {r.detail}")
    print("\nLedger (all recorded calls, by Pacific quota day):")
    for row in ledger_rows:
        print(
            f"  {row.quota_day} {row.model_id:<20} requests={row.requests} "
            f"in={row.input_tokens} out={row.output_tokens} thought={row.thought_tokens} "
            f"usd={row.cost_usd:.6f}"
        )
    return 0 if all(r.ok for r in results) else 1


def _corpus_fetch() -> int:
    entry = download.fetch(download.ECFR_TITLE_8, RAW_TITLE_8)
    download.record(MANIFEST, entry)
    print(f"{entry.url}: {entry.size_bytes} bytes, sha256 {entry.sha256[:12]}")
    return 0


def _corpus_build() -> int:
    count = build.build_f1_corpus(RAW_TITLE_8, download.ECFR_TITLE_8, F1_CORPUS)
    print(f"{F1_CORPUS}: {count} provisions")
    return 0


def _index() -> int:
    settings = get_settings()
    with closing(build_models(settings)) as models, _connect() as conn:
        store.create_schema(conn, models.embedder.dimensions)
        count = store.load_corpus(conn, F1_CORPUS, models.embedder)
    print(f"indexed {count} provisions from {F1_CORPUS}")
    return 0


def _search(query: str) -> int:
    settings = get_settings()
    with closing(build_models(settings)) as models, _connect(autocommit=True) as conn:
        hits = store.search(conn, models.embedder, query)
    for hit in hits:
        print(f"{hit.score:.4f}  {hit.citation}  {hit.body[:90]}")
    return 0


def _ask(message: str, as_of: date) -> int:
    settings = get_settings()
    with closing(build_models(settings)) as models, _connect(autocommit=True) as conn:
        services = pipeline.Services(
            models.generator,
            models.decision,
            models.embedder,
            conn,
            settings.generation_thinking_level,
        )
        reply = pipeline.answer(message, as_of, services)
    print(pipeline.render(reply))
    return 0


def _eval_retrieval(output: Path, eval_set: Path, *, hyde: bool, rerank: bool) -> int:
    settings = get_settings()
    items = retrieval_eval.load_items(eval_set)
    level = settings.generation_thinking_level
    with closing(build_models(settings)) as models, _connect(autocommit=True) as conn:
        passage_for = (
            (lambda q: hyde_search.hypothetical_passage(models.generator, q, level))
            if hyde
            else None
        )
        reorder = (lambda q, cs: _reranked(conn, models.decision, q, cs)) if rerank else None
        ranked = retrieval_eval.run(conn, models.embedder, items, passage_for, reorder)
    scores = retrieval_eval.metrics(ranked)
    versus_vector = {
        arm: {name: asdict(interval) for name, interval in by_metric.items()}
        for arm, by_metric in retrieval_eval.comparisons(ranked).items()
    }
    _save(
        output,
        eval_set,
        embedding_model=settings.embedding_model,
        generation_model=settings.generation_model if hyde else None,
        decision_model=settings.decision_model if rerank else None,
        metrics=scores,
        versus_vector=versus_vector,
        rankings=[asdict(r) for r in ranked],
    )
    for arm, values in scores.items():
        print(f"{arm:<12} " + "  ".join(f"{name}={value:.3f}" for name, value in values.items()))
    for arm, by_metric in versus_vector.items():
        print(
            f"{arm:<12} minus vector: "
            + "  ".join(
                f"{name} {i['mean']:+.3f} [{i['low']:+.3f}, {i['high']:+.3f}]"
                for name, i in by_metric.items()
            )
        )
    print(f"{len(items)} questions; raw output in {output}")
    return 0


def _eval_extraction(output: Path) -> int:
    settings = get_settings()
    items = extraction_eval.load_items(EXTRACTION_SET)
    level = settings.generation_thinking_level
    with closing(build_models(settings)) as models:
        extractions = [pipeline.extract(i.message, i.as_of, models.generator, level) for i in items]
    scores = [extraction_eval.score(i, e) for i, e in zip(items, extractions, strict=True)]
    totals = extraction_eval.summary(scores)
    _save(
        output,
        EXTRACTION_SET,
        generation_model=settings.generation_model,
        thinking_level=level,
        summary=totals,
        scores=[asdict(s) for s in scores],
        extractions=[e.model_dump(mode="json") for e in extractions],
    )
    print("  ".join(f"{name}={value}" for name, value in totals.items()))
    for s in scores:
        if s.wrong_fields or not s.out_of_scope_correct or not s.deadlines_agree:
            print(f"  {s.id}: wrong={list(s.wrong_fields)} scope_ok={s.out_of_scope_correct}")
    print(f"{len(items)} messages; raw output in {output}")
    return 0


def _eval_answers(output: Path) -> int:
    settings = get_settings()
    items = answers_eval.load_items(RETRIEVAL_DEV_SET)
    hits = answers_eval.corpus_hits(F1_CORPUS)
    level = settings.generation_thinking_level
    with closing(build_models(settings)) as models:
        scores = [
            answers_eval.evaluate(i, hits, models.generator, models.judge, level) for i in items
        ]
    totals = answers_eval.summary(scores)
    _save(
        output,
        RETRIEVAL_DEV_SET,
        generation_model=settings.generation_model,
        judge_model=settings.judge_model,
        summary=totals,
        scores=[asdict(s) for s in scores],
    )
    print("  ".join(f"{name}={value}" for name, value in totals.items()))
    print(f"{len(items)} questions; raw output in {output}")
    return 0


def _eval_pipeline(output: Path) -> int:
    settings = get_settings()
    scenarios = end_to_end.load_scenarios(PIPELINE_SET)
    with closing(build_models(settings)) as models:
        scores: list[end_to_end.ScenarioScore] = []
        for index, scenario in enumerate(scenarios, start=1):
            started = time.monotonic()
            # Open per-case and close before judging so slow judge retries cannot exceed Neon's
            # ~5-minute idle SSL timeout (D63).
            with _connect(autocommit=True) as conn:
                services = pipeline.Services(
                    models.generator,
                    models.decision,
                    models.embedder,
                    conn,
                    settings.generation_thinking_level,
                )
                reply = _strict_answer(scenario.message, scenario.as_of, services)
            score = end_to_end.evaluate(scenario, reply, models.judge)
            scores.append(score)
            elapsed = time.monotonic() - started
            print(
                f"[{index}/{len(scenarios)}] {scenario.id} ({elapsed:.1f}s)",
                file=sys.stderr,
                flush=True,
            )
    totals = end_to_end.summary(scores)
    _save(
        output,
        PIPELINE_SET,
        generation_model=settings.generation_model,
        judge_model=settings.judge_model,
        retrieval_k=pipeline.RETRIEVAL_K,
        summary=totals,
        scores=[asdict(s) for s in scores],
    )
    print("  ".join(f"{name}={value}" for name, value in totals.items()))
    print(f"{len(scenarios)} scenarios; raw output in {output}")
    return 0


def _eval_edge(output: Path, sets: list[Path]) -> int:
    settings = get_settings()
    cases = edge_eval.load_cases(sets)
    with closing(build_models(settings)) as models:
        scores: list[edge_eval.CaseScore] = []
        for index, case in enumerate(cases, start=1):
            started = time.monotonic()
            # Open per-case and close before judging so slow judge retries cannot exceed Neon's
            # ~5-minute idle SSL timeout (D63).
            with _connect(autocommit=True) as conn:
                services = pipeline.Services(
                    models.generator,
                    models.decision,
                    models.embedder,
                    conn,
                    settings.generation_thinking_level,
                )
                reply = _strict_answer(case.message, case.as_of, services)
            score = edge_eval.evaluate(case, reply, models.judge)
            scores.append(score)
            elapsed = time.monotonic() - started
            print(
                f"[{index}/{len(cases)}] {case.id} passed={score.passed} "
                f"judge_failed={score.judge_failed} ({elapsed:.1f}s)",
                file=sys.stderr,
                flush=True,
            )
    totals = edge_eval.summary(scores)
    _save(
        output,
        sets[0],
        eval_sets=[s.as_posix() for s in sets],
        generation_model=settings.generation_model,
        decision_model=settings.decision_model,
        judge_model=settings.judge_model,
        summary=totals,
        scores=[asdict(s) | {"passed": s.passed, "judge_failed": s.judge_failed} for s in scores],
    )
    overall = totals["all"]
    print("  ".join(f"{name}={value}" for name, value in overall.items()))
    print(f"{len(cases)} cases; per-category results in {output}")
    return 0


def _reranked(
    conn: psycopg.Connection, decider: DecisionModel, question: str, candidates: list[str]
) -> list[str]:
    """`candidates` with the top `rerank.CANDIDATES` reordered by the decision model."""
    head = store.by_citation(conn, candidates[: rerank.CANDIDATES])
    reordered = [hit.citation for hit in rerank.rerank(decider, question, head)]
    return reordered + candidates[rerank.CANDIDATES :]


def _strict_answer(message: str, as_of: date, services: pipeline.Services) -> pipeline.Reply:
    """An answer for an eval: a reranker failure stops the run instead of skewing its scores."""
    reply = pipeline.answer(message, as_of, services)
    if reply.rerank_error is not None:
        raise SystemExit(f"reranking failed, eval stopped: {reply.rerank_error}")
    return reply


def _save(output: Path, eval_set: Path, **fields: object) -> None:
    """Write a raw eval report with the run time, commit and eval set it came from."""
    report = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "commit": _commit(),
        "eval_set": eval_set.as_posix(),
        **fields,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")


def _commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607  # git from PATH by design
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _connect(*, autocommit: bool = False) -> psycopg.Connection:
    return psycopg.connect(
        get_settings().database_url.get_secret_value(),
        connect_timeout=20,
        autocommit=autocommit,
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="niyam")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("verify-providers", help="make one live call to each provider")
    commands.add_parser("corpus-fetch", help="download the eCFR title 8 XML from govinfo")
    commands.add_parser("corpus-build", help="parse 8 CFR 214.2(f) into the processed corpus")
    commands.add_parser("index", help="embed the processed corpus and load it into Postgres")
    search = commands.add_parser("search", help="search the indexed provisions")
    search.add_argument("query")
    evaluate = commands.add_parser("eval-retrieval", help="score retrieval arms on an eval set")
    evaluate.add_argument("output", type=Path, help="where to save the raw JSON report")
    evaluate.add_argument("--set", type=Path, default=RETRIEVAL_DEV_SET, dest="eval_set")
    evaluate.add_argument("--hyde", action="store_true", help="add the HyDE arms (1 call each)")
    evaluate.add_argument(
        "--rerank", action="store_true", help="add the reranked vector arm (1 call each)"
    )
    answers = commands.add_parser("eval-answers", help="score answers given the gold provisions")
    answers.add_argument("output", type=Path, help="where to save the raw JSON report")
    whole = commands.add_parser("eval-pipeline", help="score the whole assistant on scenarios")
    whole.add_argument("output", type=Path, help="where to save the raw JSON report")
    evaluate_x = commands.add_parser("eval-extraction", help="score fact extraction end to end")
    evaluate_x.add_argument("output", type=Path, help="where to save the raw JSON report")
    edge = commands.add_parser("eval-edge", help="score full replies on the independent sets")
    edge.add_argument("output", type=Path, help="where to save the raw JSON report")
    edge.add_argument("--set", type=Path, action="append", dest="sets", help="repeatable")
    ask = commands.add_parser("ask", help="answer an F-1 student's question")
    ask.add_argument("message")
    ask.add_argument("--as-of", type=date.fromisoformat, default=date.today(), help="YYYY-MM-DD")
    args = parser.parse_args()

    if args.command == "verify-providers":
        sys.exit(_verify_providers())
    if args.command == "corpus-fetch":
        sys.exit(_corpus_fetch())
    if args.command == "corpus-build":
        sys.exit(_corpus_build())
    if args.command == "index":
        sys.exit(_index())
    if args.command == "search":
        sys.exit(_search(args.query))
    if args.command == "eval-retrieval":
        sys.exit(_eval_retrieval(args.output, args.eval_set, hyde=args.hyde, rerank=args.rerank))
    if args.command == "eval-answers":
        sys.exit(_eval_answers(args.output))
    if args.command == "eval-pipeline":
        sys.exit(_eval_pipeline(args.output))
    if args.command == "eval-extraction":
        sys.exit(_eval_extraction(args.output))
    if args.command == "eval-edge":
        sys.exit(_eval_edge(args.output, args.sets or list(EDGE_SETS)))
    if args.command == "ask":
        sys.exit(_ask(args.message, args.as_of))
