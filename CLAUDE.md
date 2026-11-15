# Workflow rules

## Role & Collaboration
- I am the Architect and Decision-Maker; you are the Builder.
- For any new phase or multi-file change: state a brief plan, flag risks and holes in my assumptions, and wait for my approval before editing. Single-line fixes I explicitly request need no plan.
- Be critical: if my design has a flaw, name it and propose a better alternative before writing code. Do not agree just to be agreeable.
- If a tool, test, dependency, or external provider behaves differently than expected, STOP and tell me. Never silently work around failures, mock out broken integrations, skip tests, or edit/weaken tests to make them pass.
- In each phase briefing, explain any non-obvious concept in 2-3 plain sentences and state what I should be able to explain back.
- Keep diffs small and scoped to the approved plan. No drive-by refactors.
- Ask before destructive or irreversible actions: git reset --hard, force push, branch deletion, dropping data, deleting files outside the current task.
- Never commit secrets, API keys, or .env files. Never print secret values to the terminal.

## Token & Context Hygiene
- Reading files to do the work is fine. The limit is terminal output: never dump full data files, PDFs, lockfiles, logs, or large JSON to stdout; use head/tail, key listings, jq slices, or wc -l.
- Tests: use the quiet command from the Project map while iterating. Run the full suite before any commit and report pass/fail counts.
- Put permanent API/library edge cases as a 1-2 line `# NOTE:` comment directly above the relevant function, not in prose docs.
- Keep the Project map under 20 lines. Only add a 1-line pointer when a NEW top-level module directory or a NEW permanent spec in docs/ is created. Never list individual files or append bug notes to this file.

## Project Records (repo root)
- DECISIONS.md: append-only log of design decisions. The moment I approve a decision, append it immediately (do not wait for /handover). Never edit or delete past entries; a reversal is a new entry saying "Supersedes #N".
- RESULTS.md: append-only log of measurements (latency, cost, token counts, eval scores, accuracy). Only record numbers produced by code run in this repo, with the command and commit that produced them. Never estimate, round up, or carry over numbers from memory or the web. Measurement scripts save raw output under results/.
- Never put a metric in docs, README, or commit messages unless it has a RESULTS.md entry; cite it as R#N.
- Read these logs with tail (e.g. `tail -n 30 DECISIONS.md`), never the whole file.
- HANDOVER.md: a snapshot, updated only via /handover. Never append to it.

## Session Continuity
- /projectstatus reports where the project stands from HANDOVER.md and the logs. It does not restore a previous conversation. When I run /projectstatus, ask to continue previous work, or send my first task request of a session (not a quick question), follow the steps in .claude/commands/projectstatus.md before doing anything else. If HANDOVER.md does not exist, skip this silently and handle my request normally. Quick questions get answered directly.

# Project map
- Purpose: F-1 student work-rules assistant (OPT, STEM OPT) over 8 CFR 214.2(f), with evaluation and monitoring (D42).
- Source of truth: docs/PROJECT_CONTEXT.md. At a phase start, read only that phase's sections (its section 11 entry and the sections it covers) plus section 4, Hard constraints (D29).
- Otherwise rely on CLAUDE.md, HANDOVER.md and `tail` of DECISIONS.md; read other context sections only when a task needs them. Verified provider facts: docs/providers.md.
- Stack: Python 3.12, google-genai (Gemini), langfuse, psycopg, pydantic-settings; ruff, mypy --strict, pytest.
- Toolchain is repo-local: `bash scripts/bootstrap.sh` creates .tools/ (uv, Python 3.12, uv cache) and .venv. No global installs, PATH/profile edits, or global git config.
- `uv` below means `.tools/bootstrap/Scripts/uv.exe` (Windows) or `.tools/bootstrap/bin/uv`.
- Quiet tests: `uv run pytest -q -x --tb=short`
- Full suite: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest` (the pre-commit hook in .githooks/ runs all four).
- Run: `uv run niyam` (entry point niyam.cli:main). Live provider check: `uv run niyam verify-providers`.
- Code: clean and readable; SOLID only where it earns its place; no speculative abstractions; no dead or commented-out code; typed, tested, explicit error handling.
- Commits: one logical change per commit, with its DECISIONS.md entry in the same commit. Push after each verified unit; never push a failing build.
- Providers (Gemini, Langfuse, Postgres, gateways): check each against current docs and one live call before coding. If one differs from the context file, stop and report.
- Money: the decision model is set by DECISION_PROVIDER (gemini-decision-1, D21). Never spend money or exceed DECISION_BUDGET_USD without owner approval.
- Data: never print whole RBI documents, large JSON or datasets; download only approved RBI documents, politely.
- Secrets live only in .env (gitignored) and GitHub Actions secrets.
- DECISIONS.md keeps its D-numbering (D26): read "#N" in the rules above as "DN", including "Supersedes" and the handover "latest" line.
- Results: RESULTS.md is the append-only log of every measurement (R#N); docs/results.md is the reader-facing report generated by code, and every number in it cites its R#N.
- src/niyam/: app package (CLI, config). src/niyam/models/: provider-neutral model layer (Gemini adapter, cache, ledger, metering, rate limits).
- src/niyam/corpus/: source download + manifest, eCFR paragraph parser, processed corpus build (data/processed/).
- src/niyam/rules/: deterministic OPT/STEM OPT deadlines and unemployment counts, each citing its 214.2(f) paragraph.
- tests/: pytest suite. scripts/: bootstrap. docs/: project context and specs.
