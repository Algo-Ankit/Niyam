## Goal & Git state
Goal: F-1 student work-rules assistant (OPT, STEM OPT, H-1B cap-gap) over 8 CFR 214.2(f), with evals and monitoring (D42).
Branch main, last commit c978880 "Document R10 safety-first baseline context in README", pushed. Untracked: results/edge-1.log, results/edge-decline-1.log.

## Done & Verified
- D58, D59, D60b, D61: fixed rules-engine, guardrail, and scorer bugs from gold audit; separated retrieval gold from answer-eval context; relabelled h1b_cases.jsonl to D57 scope (11 in / 6 partial / 53 out). Verified: full suite, 131 passed at cc17698.
- D60: rewrote docs/PROJECT_CONTEXT.md for the F-1 product (merged via PR #1 at 6ba72b3).
- D62: opened read-only CLI/eval Postgres connections (`eval-edge`, `eval-pipeline`, `eval-retrieval`, `search`, `ask`) with `autocommit=True` so Neon `idle_in_transaction_session_timeout` cannot kill long eval runs; added stderr per-case progress logging and `tests/test_cli.py`. Verified: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest` (131 passed at 4736f7e).
- R10: completed independent decline/security eval (`results/edge-decline-1.json`, 40 cases): `passed=0.513` (`judge_failed=1` on `y031`, `no_leak=1.0`, `avoids_forbidden=1.0`, `asks_ok=1.0`, `scope_ok=0.9`, `says_required=0.538`). Verified by `uv run niyam eval-edge results/edge-decline-1.json --set evals/independent/decline_and_security.jsonl`.
- Updated `README.md` with R9 reranking results, R10 decline/security baseline table, and domain safety-first rationale (4736f7e, c978880).

## Open questions
- Owner locked R10 as the decline/security baseline for now and skipped further eval runs today; decide next session whether to run the remaining evals (`eval-answers`, `eval-pipeline`, `edge_cases.jsonl`, `h1b_cases.jsonl`) or start Phase 4 (web app / Langfuse).
- Gold of the builder-written sets (retrieval dev/test, extraction, pipeline) still awaits full owner review beyond D58-D60b fixes.

## Gotchas
- A crashed eval loses only its report: the response cache replays finished calls free, so rerun the same command.
- Background runs: end the command with `exit $status`, or a crash reports as success.
- Limits: generator 500 RPD (about 2 calls per edge case); judge gemma-4-31b-it about 4 calls/min and sometimes overloaded (503) or malformed. A new API key fixes neither.
- `uv` is `.tools/bootstrap/Scripts/uv.exe`. Pipe `< /dev/null` into one-off `uv run python` in Git Bash. Deny rules block .env, .venv, .tools.
- The review page bakes in gold as of 253cd0c; after D59-D61 gold edits, rebuild cases.js and republish it to the same URL if used.

## Next step
Wait for owner direction on whether to run the next baseline eval (`uv run niyam eval-pipeline results/pipeline-1.json` or `eval-edge` on `edge_cases.jsonl` / `h1b_cases.jsonl`) or proceed to Phase 4 (web app + Langfuse tracing).

Records: DECISIONS.md latest D62, RESULTS.md latest R10.
