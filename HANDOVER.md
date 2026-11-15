## Goal & Git state
Goal: RBI payment-regulations Q&A with evals and monitoring; Phase 0 re-verified and closed on the free tier, Phase 1 (corpus and test set) not started.
Branch main, last commit 363cc31 "Record the Gemma judge decision and benchmark results", in sync with origin/main. Uncommitted: none.

## Done & Verified
- Full suite (ruff check, format, mypy --strict, pytest 36 passed) and `uv run niyam verify-providers` 6/6 PASS (decision, generation, judge, embedding, database, langfuse). Verified by running both after the last code change (5cae7ba).
- Meter reserves in-flight calls under a lock so concurrent callers cannot overshoot quota or budget (c8786d2, D32). Verified: new concurrency test passes.
- Generator is `gemini-3.5-flash-lite` (D35, supersedes D33); hydrogen, 3.7, 3.8 rejected for speed or the 20 RPD limit (R1, R2). Verified: verify-providers generation check.
- Judge is `gemma-4-31b-it` (D36); adapter sends `thinking_level` only when set; ModelSuite has a `judge` role (R3). Verified: adapter test plus verify-providers judge check.
- Limits set from AI Studio: generator 15 RPM/250K TPM/500 RPD, judge 30/16K/14.4K, embedding 100/30K/1K, decision 200/50K/10K (D34, D35, D36).
- No spend: free tier only; paid credits and fallbacks were considered and declined by the owner.
- Restored LF line endings damaged by my Python edits (7304138); `scripts/bench_generation.py` added with raw output in results/.

## Open questions
- Should the AI Studio "used" counts be reconciled with the local ledger? Flash models showed more daily requests than we made; lite matched 1:1. Unverified, low risk.
- Ledger and cache are local SQLite in .state/ and reset on free hosting; decide handling in the Phase 4 plan.

## Gotchas
- "#N" in CLAUDE.md rules means "DN"; next decision is D37, next result R4.
- `uv` is `.tools/bootstrap/Scripts/uv.exe` on Windows; no global uv.
- Python writes CRLF on Windows: edit files with the Edit tool, or open with newline='' in scripts, or diffs explode.
- Gemma rejects `thinking_level` (HTTP 400); failed requests still count against daily quota. Gemma's binding limit is 16K tokens/min (about 4 judge calls/min); its latency is erratic.
- `gemini-2.5-*` models return 404 for new users. `gemini-3.5-flash` has no listed price or limits; do not use.
- Demo cap must stay well under the generator's 500 RPD, and CI must not run answer evals.
- `verify-providers` makes live calls that count against quota; run it only when needed.
- Read PROJECT_CONTEXT.md by section only (D29). docs/PROJECT_CONTEXT.md still says Jev and hydrogen; D21, D33, D35 supersede it.
- Deny rules block reading .env, .venv, .tools and caches.

## Next step
Start Phase 1: read docs/PROJECT_CONTEXT.md section 11 "Phase 1: Corpus and test set" plus sections 4, 6 and 7, then present the Phase 1 plan starting with the RBI document list for owner confirmation, and wait for approval before downloading anything.

Records: DECISIONS.md latest D36, RESULTS.md latest R3.
