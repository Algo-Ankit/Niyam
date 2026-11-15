## Goal & Git state
Goal: RBI payment-regulations Q&A with evals and monitoring; Phase 0 done, Phase 1 (corpus and test set) not started.
Branch main, last commit 7cb9d48 "Read the project context by phase section instead of in full", in sync with origin/main.
Uncommitted: HANDOVER.md (this file). Gitignored local backups: *.bak-20261115-* (5 files).

## Done & Verified
- Claude Code workflow setup (02e25d5): CLAUDE.md rules + project map, /handover and /resume commands, .claude/settings.json deny rules, RESULTS.md, results/, *.bak-* gitignored. Verified: grep -P non-ASCII check clean; git check-ignore shows no required file ignored.
- Pre-commit hook now also runs `pytest -q` (04ab5e1, D28). Verified: the hook ran pytest on commits 04ab5e1 and 7cb9d48.
- Decisions D26-D29 appended (D-numbering kept; RESULTS.md vs docs/results.md; hook tests; read context by phase section).
- Langfuse credentials in .env were swapped; owner fixed them. Verified: `uv run niyam verify-providers` all 5 PASS.
- Nothing under src/, tests/, scripts/, docs/ changed. Verified: `git diff 7779ddd HEAD -- src tests scripts docs` empty; full suite (ruff, format, mypy, pytest) passes.
- Pushed to origin/main.

## Open questions
- Should HANDOVER.md be committed after each /handover (setup says it must be tracked; /handover never commits)?
- Delete the *.bak-20261115-* backups now that setup is approved?

## Gotchas
- "#N" in CLAUDE.md rules means "DN" in DECISIONS.md (D26); next decision is D30.
- `uv` is `.tools/bootstrap/Scripts/uv.exe` on Windows; no global uv.
- `verify-providers` makes live provider calls that count against quota; run it only when needed.
- Read PROJECT_CONTEXT.md by section only (D29), not in full.
- Deny rules block reading .env, .venv, .tools and caches; .env.example and .state/ stay readable.
- Git reports the root as .../Desktop/Niyam, shell as .../desktop/Niyam: same folder (case-insensitive).

## Next step
Start Phase 1: read docs/PROJECT_CONTEXT.md section 11 "Phase 1: Corpus and test set" plus section 4 and the sections it covers (6 knowledge base, 7 test set), then present the Phase 1 plan, starting with the RBI document list for owner confirmation, and wait for approval.

Records: DECISIONS.md latest D29, RESULTS.md latest none.
