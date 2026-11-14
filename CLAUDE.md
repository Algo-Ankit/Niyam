# CLAUDE.md

The source of truth for this project is [`docs/PROJECT_CONTEXT.md`](docs/PROJECT_CONTEXT.md).
Read it fully before any work. Decisions and their reasons are in [`DECISIONS.md`](DECISIONS.md).
Provider facts verified against live calls are in [`docs/providers.md`](docs/providers.md).

## Roles
The owner is the architect and decides. Claude builds, verifies and briefs, one phase at a time,
and stops at each phase gate for approval.

## Environment (nothing global)
- Toolchain lives in the repo: `bash scripts/bootstrap.sh` creates `.tools/` (uv, Python 3.12,
  uv cache) and `.venv`. No global installs, PATH/profile edits, or global git config.
- Run everything through uv: `.tools/bootstrap/Scripts/uv.exe run <cmd>` (Windows) or
  `.tools/bootstrap/bin/uv run <cmd>`.
- Checks: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run pytest`.
  The git pre-commit hook (`.githooks/pre-commit`) runs the first three.

## Engineering rules
- Clean, readable code a reviewer can follow; SOLID where it earns its place, no speculative
  abstractions. No dead, unused or commented-out code. Typed (`mypy --strict`), tested,
  explicit error handling.
- One logical change per commit; record every non-trivial choice in `DECISIONS.md` in the same
  commit. Push after each verified unit of work; never push a failing build.
- Never write a number into docs, README or commit messages that code in this repo did not
  produce.
- Verify provider APIs (Jev, Gemini, Langfuse, gateways) against current docs and one live call
  before coding against them. If a provider differs from the context file, stop and report.

## Safety
- Secrets only in `.env` (gitignored) and GitHub Actions secrets. Never print, log or commit them.
- Never spend money or exceed the Jev cap (`JEV_BUDGET_USD`) without the owner's approval.
- Never print whole RBI documents, large JSON responses or datasets; inspect slices and counts.
- Download only approved RBI documents, politely.
