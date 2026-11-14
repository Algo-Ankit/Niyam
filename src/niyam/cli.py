"""Command-line entry point: `uv run niyam <command>`."""

import argparse
import sys

from niyam.config import get_settings
from niyam.models.factory import build_models
from niyam.verify import run_checks


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


def main() -> None:
    parser = argparse.ArgumentParser(prog="niyam")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("verify-providers", help="make one live call to each provider")
    args = parser.parse_args()

    if args.command == "verify-providers":
        sys.exit(_verify_providers())
