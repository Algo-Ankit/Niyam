## Goal & Git state
Goal: F-1 student work-rules assistant (OPT, STEM OPT, H-1B cap-gap) over 8 CFR 214.2(f), with evals and monitoring (D42, D51).
Branch `main`, v1 closed under D75 & D76 (R5–R15 baselines frozen; provisional R16 audit, offline CI eval gate, `docs/results.md`, Langfuse trace enrichment + web feedback + `online-eval` flywheel implemented and verified).

## Done & Verified
- Live deployment & CI: Vercel (`https://niyam-flame.vercel.app`, `web/` + `src.niyam.asgi:app`, D64–D74), GHCR image (`ghcr.io/algo-ankit/niyam-api`), `.github/workflows/ci.yml` with offline `niyam eval-gate` (56/56 checks) & `niyam eval-report --check` (D75).
- Baselines frozen (R5–R15): retrieval test rerank `1.000` hit@1 and MRR@10 (R12); whole-pipeline `scope_correct=1.0`, `deadlines_agree=1.0`, `in_scope_correct=0.9` (R14); answer quality `correct=0.85`, `grounded=0.95` (R15); independent sets `no_leak=1.0` & `asks_ok=1.0` across all 200 cases (`passed`: R10 `0.513`, R11 `0.493`, R13 `0.221`).
- R16 provisional automated audits (`results/judge-audit-1.json`, `results/gold-audit-1.json`): 30 stratified Gemma verdicts (`0.667` exact agreement, `κ=0.500` `says_required`, `κ=0.583` `correct`; 6 lenient / 4 strict) and 150 builder-written gold items (127 clean, 4 high missing `context` on `d07/d12/d15/d31`, 4 medium, 15 low). Labelled provisional pending owner spot-check.
- Langfuse & flywheel (D67, D76): enriched `LangfuseTracer` outcome metadata (still never sending raw student messages), `trace_id` on `Reply`, rate-limited `POST /api/feedback` + web `Helpful`/`Not helpful` UI (`web/src/components/Results.tsx`), `niyam online-eval` harvesting failures into `niyam-live-failures` Langfuse Dataset, and `.github/workflows/online-eval.yml` daily/manual workflow (live `--dry-run` verified against 24 traces).

## Open questions / Owner actions
- Spot-check `results/judge-audit-1.json` (30 verdicts) and `results/gold-audit-1.json` (150 items) when ready for v2.
- To activate the daily GitHub Actions `.github/workflows/online-eval.yml` cron, add 3 repository secrets in GitHub Settings > Secrets and variables > Actions: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `GEMINI_API_KEY`.
- Optional polish: rename Vercel domain, update GitHub About text.

## Gotchas
- On Windows inside the Antigravity sandbox, `tests/test_download.py::test_fetch_decompresses_names_the_client_and_hashes` hits HTTP 400 from the sandbox proxy, and `.git/` writes / network calls (`git`, Langfuse) require running outside sandbox.
- Gemini 503s can take ~30s each; live asks hit the D71 50s busy message (D73 15s model timeout). Response cache is per Vercel instance (`/tmp`).
- `uv` is `.tools/bootstrap/Scripts/uv.exe` on Windows. Never run slow evals without explicit owner permission.

## Next step (v2)
- Spot-check R16 audits; fix `d07/d12/d15/d31` gold `context`, include provision headings in `format_provisions()`, fix `_stem_filing_window` clamping in `opt.py`, improve R10/R11/R13 referral & cap-gap handling, and add a fresh held-out extraction/pipeline v2 set (incorporating harvested `niyam-live-failures` cases).

Records: DECISIONS.md latest D76, RESULTS.md latest R16.
