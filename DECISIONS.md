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

**D31. `HANDOVER.md` is committed and pushed after every `/handover`.** Each handover is its own
small commit containing only `HANDOVER.md`. The `/handover` command now ends with that commit and
push, replacing its "do not commit unless I ask" rule.
*Why:* the setup requires `HANDOVER.md` to be tracked, and leaving it staged let it drift from
the commits it describes.
*Tradeoff:* one extra commit per session in the history.

**D32. Quota and budget checks reserve in-flight calls.** `Meter` counts calls that have started
but not yet been recorded, under a lock, when it checks the daily quota and the budget.
*Why:* the check ran before the call and the ledger write after it, so parallel callers
(Phase 2 re-ranking, eval runs) could all pass the check and overshoot the limit.
*Tradeoff:* a retried call is counted twice for a moment, which errs on the side of stopping.

**D33 (supersedes D5 for the generative model). `gemini-3.5-flash` replaces `gemini-4-hydrogen`.**
Same prompt, same adapter, thinking level `low`, three questions per model (R1, R2): 3.5-flash
answered in 4.2 to 6.7 s with correct citations and a correct abstention; hydrogen took 8.2 to
36.4 s; 3.7-flash and 3.8-flash took 63 to 226 s and wrongly abstained on a question they could
answer. 3.6-flash (3.7 to 6.0 s) and 3.5-flash-lite (3.4 to 3.9 s) were also fast and correct.
*Why 3.5-flash:* fast, stable, and answered all three questions correctly; the lite model is
faster but the answer text was not compared at scale.
*Tradeoff:* three questions per model is a smoke test, not a quality comparison. Phase 3 evals
decide whether `gemini-3.6-flash` or the lite model is better; switching is one config value.

**D34. Embedding limits set from AI Studio: 100 RPM, 30K TPM, 1K RPD.** Owner-confirmed on
2026-11-15; the decision model's existing limits (200 RPM, 50K TPM, 10K RPD) matched AI Studio.
Generation limits stay unset until the `gemini-3.5-flash` row is confirmed (see D33).

**D35 (supersedes D33). `gemini-3.5-flash-lite` is the generative model, on the free tier.**
AI Studio limits (owner-confirmed): 15 RPM, 250K TPM, 500 RPD. The 3.6, 3.8 and hydrogen models
allow only 20 RPD, and `gemini-3.5-flash` has no listed limits or price. Lite was the fastest
in R2 (3.4 to 3.9 s) and answered all three benchmark questions correctly.
*Why:* the project goal is zero spend; 500 requests per day covers evaluation runs when the
decision model (10K RPD) handles most checks and the generative judge is sampled.
*Tradeoff:* the demo cap and CI must share the 500 requests; quality is checked on three
questions only, so Phase 3 evals may justify a paid model later. No fallbacks.

**D36. `gemma-4-31b-it` is the judge; the generator stays `gemini-3.5-flash-lite`.** Gemma is a
different model family from the generator, so the judge does not favour the generator's style.
Free limits (owner-confirmed): 30 RPM, 16K TPM, 14,400 RPD, so judging never competes with the
generator's 500 requests per day. Answered the benchmark correctly (R3). The adapter now sends
`thinking_level` only when set, because Gemma rejects it (HTTP 400).
*Why:* tokens per minute binds, not requests: a 4K-token judge call fits about 4 per minute, so
judging 150 answers takes about 40 minutes. Fine for offline evals, too slow for live answers.
*Tradeoff:* latency is erratic (4 to 128 s); judge agreement with human labels is unmeasured
until Phase 3 validates it, as the context file requires. `gemma-4-26b-a4b-it` is the faster
fallback by config, not automatic.

**D37. Re-scope from RBI payment regulations to US consumer payments regulation.** Owner-approved
on 2026-11-15. Both RBI's Disclaimer ("caching and links to, and the framing of this Web Site or
any of the contents are prohibited") and NPCI's terms (same clause, plus a robots.txt that blocks
unnamed crawlers) grant no licence to store or quote their text, so a hosted corpus is a legal
risk. Supersedes the RBI/NPCI corpus scope in docs/PROJECT_CONTEXT.md sections 1, 4, 6 and 7.
*Why:* US federal government works are public domain (17 U.S.C. 105; CFPB states "Information
created by the CFPB is in the public domain"), eCFR is keyless, and Reg E and Reg Z come as
structured XML with the official commentary (Supplement I). Phase 0 stack and models are unchanged.
*Tradeoff:* the India angle is lost. Verified only by agent web research and one eCFR fetch of
12 CFR 1005.6; not yet checked by code in this repo. CFPB funding litigation is unverified.

**D38. Sources are official government text only.** Owner-approved on 2026-11-15. No law-firm,
blog or commentary text is indexed; it may only help locate an official document. Conflicts
between sources are resolved from the primary text, with the page and date recorded.
*Why:* a wrong paraphrase would corrupt both answers and evals. The first research pass wrongly
called the 2016 India KYC direction repealed; the repeal clause showed otherwise.

**D39. The product is a Compliance Checker, with idea triage as its second mode.** Owner-approved
on 2026-11-15. Input is a policy, terms or procedure document (or a short product idea).
Output is a findings table: obligation, clause cited, status (compliant, non-compliant, missing,
unclear), quote from the user's text, quote from the regulation, suggested fix, plus a "not
checked" list. Idea triage never says "this is legal": it lists which provisions in the corpus
apply and names areas outside the corpus (state money-transmitter licensing, AML) as not checked.
Obligations are built once from clauses into a reviewed register. Evaluated with seeded-defect
documents and a hand-written idea set, both owner-reviewed.
*Why:* a concrete user and a checkable output; the eval is objective and the abstention list
keeps it honest. *Tradeoff:* the register and seeded defects are hand-built, and one document
check needs about 20 to 30 judgments, so per-obligation judging goes to the decision model
(10K RPD) and only the summary to the generator (500 RPD). Not legal advice; US consumer payments only.

**D40. The product is a bank and card dispute assistant.** Owner-approved on 2026-11-15.
Supersedes D39. Input: a consumer's account of a disputed transaction (what happened, dates,
account type). Output, always the same shape: which rule applies (Reg E or Reg Z billing error)
with the paragraph cited, the consumer's maximum liability, the consumer's and the bank's
deadlines as dates, a dispute letter citing the regulation, and a "not covered" list (authorized
push-payment scams, state law, AML). The model only extracts facts; liability and deadlines are
computed by deterministic code; retrieval supplies the cited text. Corpus: 12 CFR 1005 and
1026.2, 1026.12, 1026.13, each with Supplement I. CFPB Reg E FAQs and Consumer Complaint
Database narratives are test data only, never indexed. Evaluated per stage: extraction (labelled
narratives), routing (complaint product labels), rules engine (pytest from regulation examples),
retrieval recall@k and MRR (gold paragraph from the rules engine and FAQ citations), grounding
and FAQ agreement (judge, calibrated on about 30 owner labels), abstention, and a deterministic
letter checklist.
*Why:* a concrete user who is losing money, a fixed output, and gold data written by the
regulator rather than by us. *Tradeoff:* complaint product labels are consumer-chosen and noisy;
FAQ count and complaint-database terms are unverified. Legal information, not legal advice.

**D41. The product is a YouTube video assistant.** Owner-approved on 2026-11-15. Supersedes D37,
D38 and D40. consumerfinance.gov returns 403 even for robots.txt to a clearly named client, so
D40's gold data cannot be fetched without spoofing. Two modes: (1) paste a public YouTube link
and get a timestamped summary and answers with clickable timestamps, or "not in this video";
(2) state requirements and get recommended videos. Video content comes only from the Gemini API's
YouTube URL input (Interactions API, `{"type": "video", "uri": ...}`; one live call with
gemini-3.5-flash-lite succeeded, 13,567 video tokens). Search and metadata come only from the
YouTube Data API. No transcript scraping, youtube-transcript-api, yt-dlp or downloads: the
YouTube API Developer Policies forbid scraping or obtaining scraped YouTube data. Stored data
expires after 30 days (the policy limit for Non-Authorized Data, which must then be deleted or
refreshed). The finder must not compute scores from API statistics (the policy forbids derived
metrics); it uses the API's own ordering and filters, and fit is judged by Gemini watching the
candidates.
*Why:* a useful, fixed product built only on sanctioned Google interfaces, reusing the Phase 0
stack. *Tradeoff:* the YouTube URL input is a preview feature and its pricing and limits may
change; free tier is 8 hours of YouTube video per day, public videos only; video tokens can
exceed the generator's 250K tokens-per-minute limit on long videos (tokens per second not yet
measured); YouTube Data API allows 100 search.list calls per day.

**D42. The product is an F-1 student work-rules assistant (OPT and STEM OPT).** Owner-approved on
2026-11-15. Supersedes D41; D38 (official government text only) applies again. Input: an F-1
student's situation in plain words (program end date, OPT or STEM OPT dates, employment gaps,
degree). Output, always the same shape: the rules that apply with the paragraph cited, the
student's deadlines as dates, unemployment days used against the limit, and a "not covered" list
(H-1B, green card, taxes, anything needing the DSO or a lawyer). The model only extracts facts;
dates and day counts are computed by deterministic code; retrieval supplies the cited text.
Corpus: 8 CFR 214.2(f) from the govinfo bulk eCFR XML (title 8 last modified 2026-10-15) and
DHS Study in the States pages; both answered a clearly named client with 200 and their robots.txt
allows the paths used. Evaluated per stage: extraction, rules engine (pytest from the regulation
text), retrieval recall@k and MRR, grounding and correctness (calibrated judge), abstention.
*Why:* a specific user with a costly problem (loss of status), no free tool that does the date
math, and verified sources. *Tradeoff:* immigration rules change (DHS proposed an OPT fee rule on
2026-10-08), so the corpus needs a freshness check; a ready-made DHS FAQ gold set is unconfirmed.
Information, not legal advice.

**D43. Corpus v1 is 8 CFR 214.2(f) only; processed text is committed.** Decided by the builder
on 2026-11-15 under the owner's delegation of build decisions. Source: govinfo bulk eCFR title 8
(current as of 2026-10-14), parsed into 203 provisions with their citation path and headings;
the parser rejects any label that breaks the CFR numbering sequence. The processed JSON is
committed because US federal works are public domain (17 U.S.C. 105); the 5.4 MB raw XML stays
gitignored and is reproducible with `niyam corpus-fetch`. Study in the States pages are deferred:
the current regulation sets 30-day limits (Form I-765 filing after the program end date, the OPT
start date, and the departure period), and DHS pages written for earlier rules may disagree;
per D38 the regulation wins, and a page enters only after a check that it matches the current text.
*Why:* the primary text alone answers every deadline the rules engine computes. *Tradeoff:*
explanatory DHS prose is absent until pages are checked one by one.

**D44. Rules engine conventions where the regulation is silent.** Decided by the builder on
2026-11-15 under the owner's delegation. Each convention is shown to the user as an assumption
on the finding it affects: (1) unemployment days count from the OPT EAD start date (SEVP
practice; 214.2(f)(10)(ii)(E) gives only the 90 and 150 limits); (2) every job the student lists
counts as qualifying employment; (3) "business days" exclude weekends and the 5 U.S.C. 6103
federal holidays, moved to the observed weekday; (4) a 24-month STEM period starting on day D
ends the day before the same date 24 months later; (5) "completion of study" for the 14-month
limit is the program end date. Rules run only when their facts are known; otherwise the missing
fact names are returned so the assistant asks instead of guessing.
*Why:* deadlines must come from code with stated assumptions, never from a model. *Tradeoff:*
conventions (1) and (4) may differ from SEVIS or USCIS practice in edge cases.

**D45. Embedding batches are metered per text; retrieval is hybrid with reciprocal rank fusion.**
Owner-approved on 2026-11-15. The Gemini free tier counts each text in an embedding batch as one
request (measured: 429 at batches of 40 against the 100 requests/minute limit), so the meter,
rate limiter and ledger now carry a request count per call, and documents are embedded in
batches of 90. Provisions live in Postgres (Neon) with a generated English tsvector and a
768-dimension pgvector column; a query runs keyword search (words ORed, ranked by ts_rank_cd)
and exact vector search, fused by reciprocal rank (k = 60). Heading-only provisions are not
indexed; their headings lead each child's search text.
*Why:* a batch of 40 must not be counted as 1 request, or every index run fails. *Tradeoff:*
indexing the 181 provisions takes about a minute and uses about 181 of the 1,000 daily requests.

**D46. Assistant pipeline: two generator calls, code-checked output.** Decided by the builder on
2026-11-15 under the owner's delegation. `niyam ask` runs: (1) the generator extracts
StudentFacts, a one-sentence question and out-of-scope topics (fixed list: H-1B, green card,
taxes, travel, other statuses); (2) the rules engine computes findings; (3) hybrid search
(k = 6) plus the findings' own paragraphs give the provisions; (4) the generator explains using
only those; (5) code withholds the explanation if it cites a provision it was not given, states
an ISO date the rules engine did not compute, or writes a date in words or slashes (which
cannot be checked). Findings, assumptions, missing facts, "not covered" and the disclaimer are
rendered by code, not by the model.
*Why:* the model can phrase but can never be the source of a deadline. *Tradeoff:* about 2
generator requests per question against 500 per day; a withheld explanation still shows the
computed findings.

**D47. Production retrieval is the vector arm alone.** Decided by the builder on 2026-11-15 under
the owner's delegation. Supersedes the fusion part of D45. On R4, vector search scores hit@1
0.857 and MRR@10 0.903; hybrid fusion scores 0.486 and 0.614, because the keyword arm (0.086 and
0.271) gets equal weight and pushes good vector results down. Keyword and hybrid stay in the
eval as comparison arms; the tsvector column stays for them.
*Why:* the measured best arm. *Tradeoff:* the eval set is builder-written and small (35
questions), so the choice should be re-checked once the owner has reviewed the set.
