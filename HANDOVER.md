## Goal & Git state
Goal: F-1 student work-rules assistant (OPT, STEM OPT, H-1B cap-gap) over 8 CFR 214.2(f), with evals and monitoring (D42).
Branch main, last commit 03beb90 "Update session handover", pushed. Untracked: results/edge-1.log, results/edge-decline-1.log, results/pipeline-1.log, results/pipeline-1.started-at, results/retrieval-test-rerank-1.log.

## Done & Verified
- Phase 4 & deployment completed: live on Vercel at https://niyam-flame.vercel.app (`web/` + `src.niyam.asgi:app`, D64–D74) and published container `ghcr.io/algo-ankit/niyam-api` (`122d49a`); GitHub CI green.
- D63: scoped eval Postgres connections per case in `src/niyam/cli.py` and closed before judging so >300s judge calls do not hit Neon's 5-min idle SSL timeout (`8bfb014`).
- R11: independent H-1B eval (`results/edge-h1b-1.json`, 70 cases): `passed=0.493` (`judge_failed=1`: `h070`, `scope_ok=0.814`, `deadlines_ok=0.556`, `says_required=0.551`).
- R12: retrieval test split rerank confirmed (`results/retrieval-test-rerank-1.json`, 35 questions): vector+rerank `1.000` hit@1 and MRR@10.
- R13: independent edge-cases eval (`results/edge-cases-1.json`, 90 cases): `passed=0.221` (`judge_failed=4`: `x022`, `x045`, `x057`, `x061`, `scope_ok=0.867`, `deadlines_ok=0.571`, `counts_ok=0.947`, `says_required=0.326`).
- R14: whole-pipeline eval (`results/pipeline-1.json`, 40 scenarios): `scope_correct=1.0`, `deadlines_agree=1.0`, `in_scope_shown=0.933`, `in_scope_cites_gold=0.967`, `in_scope_correct=0.9`, `in_scope_grounded=0.933`, `unanswerable_abstained=1.0`.
- R15: answer-quality eval (`results/answers-1.json`, 40 questions): `answerable=0.875`, `shown=1.0`, `cites_gold=0.95`, `correct=0.85`, `grounded=0.95`.
- Verified: full suite (`uv run ruff check .`, `ruff format --check .`, `mypy`, `pytest` 163 passed at `b5fdc72`).

## Open questions
- Gold of builder-written sets (retrieval dev/test, extraction, pipeline) still awaits owner review; judge uncalibrated (owner labels ~30 verdicts).
- Optional: rename Vercel domain (Project > Settings > Domains); paste new GitHub About text drafted in the archived 4c session.

## Gotchas
- D63 adds ~0.5s TLS handshake per cached replay; if a judge call takes >300s, Neon can still close a freshly opened connection during a slow `extract` (>50s) before `vector_ranking`.
- Gemini 503s can take ~30s each; live asks then hit the D71 busy message (D73 15s model timeout). Response cache is per Vercel instance (`/tmp`).
- A crashed eval loses only its report: the response cache replays finished calls free. Background runs: end with `exit $status`.
- `uv` is `.tools/bootstrap/Scripts/uv.exe`; pipe `< /dev/null` into one-off `uv run python`. Deny rules block .env, .venv, .tools.

## Next step
Inspect R11/R13 misses (`says_required`: `h1b_cases` `cap_gap` 0.0, `edge_cases` `scope_boundaries` 0.0) and calibrate `gemma-4-31b-it` against owner labels on ~30 verdicts.

Records: DECISIONS.md latest D74, RESULTS.md latest R15.
