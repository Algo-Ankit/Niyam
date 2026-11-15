# Decisions

Every non-trivial choice, with the reason and the tradeoff. Newest at the bottom.
The owner can overturn any entry; the reversal is recorded as a new entry.

## Seeded from the project context (section 12), 2026-11-14

| # | Decision | Why | Tradeoff |
|---|---|---|---|
| D1 | Use case: RBI payment regulations Q&A. | Real public documents, an official FAQ test set, and a domain where wrong answers matter. | Narrow audience; corpus needs careful in-force checks. |
| D2 | Official RBI text only in the knowledge base. | Every answer traces to the regulator. | No plain-language commentary to help retrieval. |
| D3 | FAQs are the test set and are never indexed. | Keeps evaluation honest. | FAQ phrasings cannot help answer live questions. |
| D4 | Abstain over guess. | A wrong compliance answer is worse than no answer. | Some answerable questions will be declined. |
| D5 | Jev for relevance, scope and support checks; `gemini-4-hydrogen` writes answers. | Use a decision model for decisions and a generative model for text. | Two providers to integrate and monitor. |
| D6 | Numbers and dates are verified by code. | The decision model is weak at counting and date comparison. | Needs robust parsing of Indian number formats. |
| D7 | Postgres for everything (chunks, vectors, keyword index, logs). | One database, one service. | Not the fastest vector search at scale; irrelevant at this size. |
| D8 | Dated snapshot, no live crawling. | Reproducible, testable answers. | Answers go stale as regulations change. |
| D9 | The automatic judge is validated against the owner's hand grades before its scores are reported. | Judge scores are only as trustworthy as their agreement with a human. | Owner time; small sample gives wide intervals. |
| D10 | Jev budget cap 5 USD, enforced in code. | Hard cost ceiling for a portfolio project. | Calls stop when the cap is reached. |

## Phase 0, 2026-11-14

**D11. Toolchain lives inside the repo.** `uv` was not installed and system Python is 3.13. uv is
installed into `.tools/bootstrap` (a throwaway venv, pip cache disabled), CPython 3.12 into
`.tools/python` with `--no-bin --no-registry`, and the uv cache into `.tools/uv-cache`.
`pyproject.toml` sets `python-downloads = "manual"` so uv never fetches a Python into the user
profile. `scripts/bootstrap.sh` reproduces the setup.
*Why:* the owner's rule forbids global or user-level installs. *Tradeoff:* commands use the
longer path `.tools/bootstrap/Scripts/uv.exe` instead of `uv`; about 100 MB inside the repo
folder (gitignored).

**D12. No Makefile; tasks are uv-run commands.** `make` is not installed on the owner's Windows
machine and installing it would be a global change. Tasks such as `verify-providers` are exposed
as a `niyam` console command run with `uv run`. *Tradeoff:* the context file names
`make verify-providers`; the equivalent is `uv run niyam verify-providers`.

**D13. Plain git hook instead of the `pre-commit` framework.** `.githooks/pre-commit` runs ruff
(lint and format check) and mypy through uv, and blocks any staged `.env` file. Enabled with the
repo-local `core.hooksPath`. *Why:* the framework stores hook environments in the user profile
and adds a dependency for three commands. *Tradeoff:* no hook marketplace; acceptable for three
checks.

**D14. `mypy --strict` added to the dev tools.** Not listed in the context file's stack. *Why:*
the owner asked for production-grade typed code; a type checker is the only way to hold that
claim. *Tradeoff:* more annotation effort; the owner may drop it.

**D15. Git identity is repo-local and uses the GitHub noreply address.** The repo is public, so
the owner's personal email is not written into commit metadata. Global git config is untouched.

**D16. Build on the existing GitHub history.** `origin/main` already had a README; the local repo
was reset onto it instead of starting a second root commit. `KICKOFF_PROMPT.md` is a working
prompt, not project documentation, and is excluded locally (`.git/info/exclude`).

**D17. Push cadence.** Commit locally per logical change; push after each verified unit of work,
never a failing build. *Why:* each push will trigger CI with quota-consuming eval runs from
Phase 4.

**D18. Project name stays Niyam** (context default) until the owner renames it.

**D19. If Jev cannot be reached for free, stop and ask** (context default, section 5). No credits
are bought; no-Jev mode needs the owner's approval.

**D20. Neon direct (unpooled) connection string for now.** The pooled endpoint runs PgBouncer in
transaction mode, which conflicts with server-side prepared statements and schema migrations.
Revisit for the deployed app in Phase 4.

**D21 (supersedes D5 for the decision model). `gemini-decision-1` replaces Jev.** The Vercel
route to Jev returned HTTP 403 `customer_verification_required` (a card on file is needed to
unlock the free credit). The owner chose not to add a card or buy credits. gemini-decision-1
runs on the existing Gemini key, free tier, and answers many yes/no questions over one shared
input in a single request (input billed once). *Tradeoff:* loses the Jev story; the
`DecisionModel` interface stays provider-neutral so Jev can be added later as a second adapter.
Env vars renamed: `DECISION_PROVIDER`, `DECISION_BUDGET_USD` (was `JEV_*`).

**D22. Our own response cache only.** No provider-side context caching anywhere
(gemini-4-hydrogen supports implicit caching only; the Decisions API supports none).

**D23. Lowest thinking level (`low`) by default** for generation and the judge; raise only if
Phase 3 evals justify it.

**D24. Embeddings: `gemini-embedding-2` at 768 dimensions.** Fits pgvector's 2,000-dimension
HNSW limit, auto-normalised by the provider. Each text is sent as its own `Content`, because a
plain list is aggregated into one vector.

**D25. Model stack composed as `Cached(Metered(Adapter))`.** Cache hits never consume quota.
`Meter` enforces daily quota (Pacific quota day), budget, per-minute limits, and stops on the
first 429 (`max_rate_limit_retries=0`) until free-tier limits are confirmed from AI Studio.

## Workflow setup, 2026-11-15

**D26. DECISIONS.md keeps its D-numbering.** The workflow rules in `CLAUDE.md` refer to entries
as "#N"; read that as "DN", including "Supersedes #N" and the handover "latest #N" line.
Existing entries are not reformatted or renumbered.
*Why:* one numbering scheme in one file; D1 to D25 are already cited elsewhere.
*Tradeoff:* the rule text and the log use different spellings, bridged by a Project map line.
*Rejected:* switching new entries to `## #N` headings (two schemes in one file).

**D27. Two results files with separate roles.** `RESULTS.md` at the repo root is the
append-only log of every measurement (R#N), each with its command, commit and raw output under
`results/`. `docs/results.md` is the reader-facing report, generated by code, and every number
in it cites its R#N entry.
*Why:* the log stays the single source of numbers; the report can be regenerated without
editing history.
*Tradeoff:* two files to keep consistent; the report is regenerated, never edited by hand.

**D28. The pre-commit hook also runs `pytest -q`.** The full suite runs offline (verified with
socket connections blocked) and in about a second, so it gates every commit alongside ruff and
mypy. The live `verify-providers` check stays manual.
*Why:* a failing test can no longer be committed by accident.
*Tradeoff:* commits wait for the suite; revisit if it stops being fast or offline.

**D29. Read `docs/PROJECT_CONTEXT.md` by section, not in full.** At the start of a phase, read
only that phase's sections (its entry in section 11 and the sections it covers) plus section 4,
Hard constraints. Otherwise rely on `CLAUDE.md`, `HANDOVER.md` and the tail of `DECISIONS.md`,
and read other sections only when a task needs them. Replaces the "read it fully before any
work" rule from the Phase 0 `CLAUDE.md`.
*Why:* the context file is long; reading all of it every session spends context on sections
that do not apply to the current phase.
*Tradeoff:* a rule from an unread section can be missed; section 4 is always read to cover the
constraints that apply everywhere.

**D30. The custom `/resume` command is renamed `/projectstatus`.** The file moves to
`.claude/commands/projectstatus.md`, and `CLAUDE.md` and `.claude/setup-instructions.md` point to
it. It reports where the project stands from `HANDOVER.md` and the logs; it does not restore a
previous conversation.
*Why:* the old name shadowed Claude Code's built-in `/resume` session picker and suggested the
command restores a conversation.
*Tradeoff:* the habit of typing `/resume` now opens the built-in picker instead.
