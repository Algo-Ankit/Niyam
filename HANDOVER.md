## Goal & Git state
Goal: F-1 student work-rules assistant (OPT, STEM OPT, H-1B cap-gap) over 8 CFR 214.2(f), with evals and monitoring (D42).
Branch main, last commit 122d49a "Document the live Vercel deployment and the published container", pushed. Untracked: results/edge-1.log, results/edge-decline-1.log, results/retrieval-test-rerank-1.log.

## Done & Verified
- Phase 4 shipped. Verified: full suite 156 passed at 122d49a (pre-commit hook); GitHub CI green (python, web, container).
- D64: `POST /api/ask` streams stage events (SSE) then the reply; per-IP hourly limit + per-quota-day cap; generic busy/internal errors. Verified: tests/test_api.py and one live ask.
- D66: TypeScript site in `web/` (Vite, React, Motion), recorded-answer replay. Verified: `npm run build --prefix web`, browser check desktop/mobile/light.
- D67 Langfuse tracing; D69 flush after reply. Verified: owner saw the live trace in Langfuse.
- D68/D69: Dockerfile + HEALTHCHECK; CI builds, smoke-tests and publishes `ghcr.io/algo-ankit/niyam-api` (public; verified by anonymous manifest pull).
- D69/D70/D71: live on Vercel at https://niyam-flame.vercel.app (Services `api` + `web`, one origin); 50 s ask deadline. Verified: live `/api/health`, live ask (all 6 stages + reply), site in Chrome.
- R12: rerank confirmed on retrieval test split. Unverified: per-IP limit reads real IP on Vercel (relies on Vercel docs for `x-real-ip`).

## Open questions
- Gold of builder-written sets (retrieval dev/test, extraction, pipeline) still awaits owner review; judge uncalibrated (owner labels ~30 verdicts).
- Optional: rename Vercel domain (Project > Settings > Domains); paste new GitHub About text drafted in the archived 4c session.

## Gotchas
- Antigravity's `eval-edge` on `edge_cases.jsonl` was still running at handover (writes results/edge-cases-1.json); it shares the Gemini quota with the live site.
- While an eval runs, `niyam.exe` is locked: commit with `UV_NO_SYNC=1` so the hook's `uv run` skips reinstalling (checks still run).
- Gemini 503s can take ~30 s each; live asks then hit the D71 busy message. Response cache is per Vercel instance (`/tmp`).
- Vercel resolves the service entrypoint from the repo root: keep `src.niyam.asgi:app` in vercel.json. Generated deployment URLs are login-protected; the production domain is public.
- A crashed eval loses only its report: the response cache replays finished calls free. Background runs: end with `exit $status`.
- `uv` is `.tools/bootstrap/Scripts/uv.exe`; pipe `< /dev/null` into one-off `uv run python`. Deny rules block .env, .venv, .tools.

## Next step
When results/edge-cases-1.json exists, append it to RESULTS.md as R13 (command `uv run niyam eval-edge results/edge-cases-1.json --set evals/independent/edge_cases.jsonl`, its commit from the JSON), then run `uv run niyam eval-pipeline results/pipeline-1.json` in the background.

Records: DECISIONS.md latest D71, RESULTS.md latest R12.
