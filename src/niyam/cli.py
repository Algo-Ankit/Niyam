"""Command-line entry point: `uv run niyam <command>`."""

import argparse
import json
import subprocess
import sys
from contextlib import closing
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path

import psycopg

from niyam.assistant import pipeline
from niyam.config import get_settings
from niyam.corpus import build, download
from niyam.evals import extraction as extraction_eval
from niyam.evals import retrieval as retrieval_eval
from niyam.models.factory import build_models
from niyam.retrieval import store
from niyam.verify import run_checks

RAW_TITLE_8 = Path("data/raw/ECFR-title8.xml")
MANIFEST = Path("data/manifest.json")
F1_CORPUS = Path("data/processed/8-cfr-214.2-f.json")
RETRIEVAL_SET = Path("evals/retrieval.jsonl")
EXTRACTION_SET = Path("evals/extraction.jsonl")


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
    with closing(build_models(settings)) as models, _connect() as conn:
        hits = store.search(conn, models.embedder, query)
    for hit in hits:
        print(f"{hit.score:.4f}  {hit.citation}  {hit.body[:90]}")
    return 0


def _ask(message: str, as_of: date) -> int:
    settings = get_settings()
    with closing(build_models(settings)) as models, _connect() as conn:
        services = pipeline.Services(
            models.generator, models.embedder, conn, settings.generation_thinking_level
        )
        reply = pipeline.answer(message, as_of, services)
    print(f"Question: {reply.extraction.question}")
    print()
    for finding in reply.assessment.findings:
        print(f"- [{finding.status}] {finding.summary} ({finding.citation})")
        for assumption in finding.assumptions:
            print(f"    assumption: {assumption}")
    if reply.assessment.missing:
        print()
        print(f"Tell me these to compute more deadlines: {', '.join(reply.assessment.missing)}")
    print()
    if reply.explanation is not None:
        print(reply.explanation.explanation)
        print(f"Sources: {', '.join(reply.explanation.citations)}")
    else:
        print(f"Explanation withheld: it {reply.rejected_reason}.")
    if reply.extraction.out_of_scope:
        print()
        print(f"Not covered: {', '.join(reply.extraction.out_of_scope)}. {pipeline.NOT_COVERED}")
    print()
    print(pipeline.DISCLAIMER)
    return 0


def _eval_retrieval(output: Path) -> int:
    settings = get_settings()
    items = retrieval_eval.load_items(RETRIEVAL_SET)
    with closing(build_models(settings)) as models, _connect() as conn:
        ranked = retrieval_eval.run(conn, models.embedder, items)
    scores = retrieval_eval.metrics(ranked)
    report = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "commit": _commit(),
        "eval_set": RETRIEVAL_SET.as_posix(),
        "items": len(items),
        "embedding_model": settings.embedding_model,
        "metrics": scores,
        "rankings": [asdict(r) for r in ranked],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    for arm, values in scores.items():
        print(f"{arm:<8} " + "  ".join(f"{name}={value:.3f}" for name, value in values.items()))
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
    report = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "commit": _commit(),
        "eval_set": EXTRACTION_SET.as_posix(),
        "items": len(items),
        "generation_model": settings.generation_model,
        "thinking_level": level,
        "summary": totals,
        "scores": [asdict(s) for s in scores],
        "extractions": [e.model_dump(mode="json") for e in extractions],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print("  ".join(f"{name}={value}" for name, value in totals.items()))
    for s in scores:
        if s.wrong_fields or not s.out_of_scope_correct or not s.deadlines_agree:
            print(f"  {s.id}: wrong={list(s.wrong_fields)} scope_ok={s.out_of_scope_correct}")
    print(f"{len(items)} messages; raw output in {output}")
    return 0


def _commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607  # git from PATH by design
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _connect() -> psycopg.Connection:
    return psycopg.connect(get_settings().database_url.get_secret_value(), connect_timeout=20)


def main() -> None:
    parser = argparse.ArgumentParser(prog="niyam")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("verify-providers", help="make one live call to each provider")
    commands.add_parser("corpus-fetch", help="download the eCFR title 8 XML from govinfo")
    commands.add_parser("corpus-build", help="parse 8 CFR 214.2(f) into the processed corpus")
    commands.add_parser("index", help="embed the processed corpus and load it into Postgres")
    search = commands.add_parser("search", help="hybrid search over the indexed provisions")
    search.add_argument("query")
    evaluate = commands.add_parser("eval-retrieval", help="score retrieval arms on the eval set")
    evaluate.add_argument("output", type=Path, help="where to save the raw JSON report")
    evaluate_x = commands.add_parser("eval-extraction", help="score fact extraction end to end")
    evaluate_x.add_argument("output", type=Path, help="where to save the raw JSON report")
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
        sys.exit(_eval_retrieval(args.output))
    if args.command == "eval-extraction":
        sys.exit(_eval_extraction(args.output))
    if args.command == "ask":
        sys.exit(_ask(args.message, args.as_of))
