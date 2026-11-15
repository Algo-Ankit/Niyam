"""Command-line entry point: `uv run niyam <command>`."""

import argparse
import sys
from pathlib import Path

from niyam.config import get_settings
from niyam.corpus import build, download
from niyam.models.factory import build_models
from niyam.verify import run_checks

RAW_TITLE_8 = Path("data/raw/ECFR-title8.xml")
MANIFEST = Path("data/manifest.json")
F1_CORPUS = Path("data/processed/8-cfr-214.2-f.json")


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


def main() -> None:
    parser = argparse.ArgumentParser(prog="niyam")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("verify-providers", help="make one live call to each provider")
    commands.add_parser("corpus-fetch", help="download the eCFR title 8 XML from govinfo")
    commands.add_parser("corpus-build", help="parse 8 CFR 214.2(f) into the processed corpus")
    args = parser.parse_args()

    if args.command == "verify-providers":
        sys.exit(_verify_providers())
    if args.command == "corpus-fetch":
        sys.exit(_corpus_fetch())
    if args.command == "corpus-build":
        sys.exit(_corpus_build())
