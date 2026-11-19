## Goal & Git state
Goal: F-1 student work-rules assistant (OPT, STEM OPT, H-1B cap-gap) over 8 CFR 214.2(f), with evals and monitoring (D42).
Branch main, last commit 253cd0c "Add the independent eval sets for eval-edge (D54)", pushed. Untracked: results/edge-1.log (empty, from a failed 16-Nov run), results/edge-decline-1.log (run in progress).

## Done & Verified
- Previous handover (D39, US payments scope) was 15 decisions stale; state rebuilt from DECISIONS.md, RESULTS.md and git. Repo is at D54 / R9.
- Committed the 200 independent eval cases in evals/independent/ (90 edge, 70 H-1B, 40 decline/security). Verified: pre-commit hook passed ruff, format, mypy, pytest (108 passed); pushed.
- Started `uv run niyam eval-edge results/edge-decline-1.json --set evals/independent/decline_and_security.jsonl` in the background. Unverified: not finished at handover time.
- Local ledger shows all logged calls at $0.00, DECISION_BUDGET_USD is 0, and no calls on 2026-11-19 before this run. The 16-Nov edge attempt made 20 generator and 9 judge calls, then died with no report.

## Open questions
- Owner review of the model-written gold in evals/independent/ (owner reviews, never types gold).
- Antigravity (Gemini) role: proposed as an independent gold cross-check that sends only disagreements to the owner; caveat that it shares a model family with our decision model and judge. Not decided.
- Make eval-edge save after each case so a crash keeps partial results? Proposed, not approved.
- Ask CFPB / Reg Z questions from the old handover are moot after the F-1 re-scope.

## Gotchas
- docs/PROJECT_CONTEXT.md has no F-1 or 214.2 content and still describes RBI/NPCI; CLAUDE.md calls it the source of truth. Trust DECISIONS.md over it until it is rewritten.
- eval-edge writes its JSON only at the end; an exception loses the whole run (the response cache in .state/ replays finished calls for free).
- Limits: generator gemini-3.5-flash-lite 500 RPD; judge gemma-4-31b-it 16K tokens/min (about 4 calls/min); decision model 10K RPD. eval-edge costs 3 to 4 requests per case (D54), so all 200 cases need more than one quota day for the generator if run together.
- `uv` is `.tools/bootstrap/Scripts/uv.exe` on Windows. Pipe `< /dev/null` into one-off `python`/`uv run` commands in Git Bash or a stray stdin read can hang.
- `verify-providers` makes live calls that count against quota. Deny rules block reading .env, .venv, .tools and caches.
- Subagent and other-model output is unverified; keep subagents on Sonnet or Opus at medium effort.

## Next step
When the decline/security run ends, read the summary in results/edge-decline-1.json and append it to RESULTS.md as R10 with command and commit 253cd0c; then run the same command with --set evals/independent/edge_cases.jsonl to results/edge-cases-1.json.

Records: DECISIONS.md latest D54, RESULTS.md latest R9.
