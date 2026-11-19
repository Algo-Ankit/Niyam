## Goal & Git state
Goal: F-1 student work-rules assistant (OPT, STEM OPT, H-1B cap-gap) over 8 CFR 214.2(f), with evals and monitoring (D42).
Branch main, last commit 1384b61 "Retry malformed judge output and keep eval-edge going on judge failure (D56, D57)", pushed. Untracked: results/edge-1.log, results/edge-decline-1.log (logs of crashed runs, no scores).

## Done & Verified
- D55: 429 and any 5xx from Gemini retried 3 times (2/4/8 s), every attempt recorded in the ledger; Interactions API errors (google.genai._gaos compat_errors) are now translated. Verified: full suite, 114 passed at 321ec31.
- D56: judges retry malformed output (3 tries); eval-edge marks a case judge_failed, leaves it out of pass rates and counts it; meter records unusable responses. Verified: full suite, 117 passed at 1384b61.
- D57: corpus stays 214.2(f); 214.2(h) not added. Measured from data/raw: (h) 583 XML paragraphs vs 181 for (f); parser refuses (h) because "(i)" is both a letter and a roman label.
- Gold review page published (private): https://claude.ai/artifact/AnwgH5vM28M6YCdCke2FS1. All 350 cases with regulation text; verdicts (ok/wrong/unsure + note) in its db collection "verdicts", owner-write only. Verified: probe write/read/delete; an interact-level write was refused. 0 verdicts so far. Builder script: scratchpad build_review.py (not in repo).
- Unverified: no eval-edge run has finished; three decline/security attempts crashed (503, then malformed judge JSON), and the last was stopped by the owner. No R10.
- Memory: agent roles saved (Claude principal; agy Neon = SDE3/lead, Hydrogen = SDE1; Haiku subagent = Claude's SDE1).

## Open questions
- Owner is checking and correcting bugs found in the gold sets now. Next session: see what changed in evals/ and verify each fix against the regulation.
- The 61 H-1B cases citing 214.2(h) need relabelling to expect a decline (D57) before that set is scored.
- Gold of the builder-written sets (retrieval dev/test, extraction, pipeline) has never had owner review.
- results/extraction-eval-3.json exists but has no RESULTS.md entry; check before reporting it.
- eval-answers and eval-pipeline have never been run.

## Gotchas
- docs/PROJECT_CONTEXT.md has no F-1 content and still describes RBI/NPCI; trust DECISIONS.md over it until it is rewritten.
- A crashed eval loses only its report: the response cache replays finished calls free, so rerun the same command.
- Background runs: end the command with `exit $status`, or a crash reports as success.
- Limits: generator 500 RPD (about 2 calls per edge case); judge gemma-4-31b-it about 4 calls/min and sometimes overloaded (503) or malformed. A new API key fixes neither.
- `uv` is `.tools/bootstrap/Scripts/uv.exe`. Pipe `< /dev/null` into one-off `uv run python` in Git Bash. Deny rules block .env, .venv, .tools.
- The review page bakes in gold as of 253cd0c; after gold edits, rebuild cases.js and republish it to the same URL.

## Next step
Run `git diff 1384b61 -- evals/` to see the owner's gold fixes, check each against data/processed/8-cfr-214.2-f.json, then propose a DECISIONS entry and commit, and rerun `uv run niyam eval-edge results/edge-decline-1.json --set evals/independent/decline_and_security.jsonl`.

Records: DECISIONS.md latest D57, RESULTS.md latest R9.
