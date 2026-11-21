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

**D48. Eval sets sized by doubling to a cap; HyDE and k = 5 tested on a dev split.** Owner-approved
on 2026-11-15. Three sets, each sized to answer its question: retrieval (60 dev questions for
tuning; the 35 R4 questions become the held-out test split; cap 190), answer quality (40 dev
questions with reference answers, judged by Gemma for correctness and grounding; cap 80), and
the whole pipeline (40 scenarios, 30 in scope and 10 out of scope or unanswerable; cap 80). A
set is doubled once, up to its cap, only if the 95% paired-bootstrap interval on the comparison
that matters includes zero; caps are fixed before the first run. Retrieval arms: vector,
HyDE (the generator writes a hypothetical regulation passage, embedded as a document) and the
two fused by reciprocal rank; the dev winner is confirmed once on the test split. The assistant
retrieves k = 5. Gold is builder-written and paragraph-anchored; judge scores stay uncalibrated
until the owner labels 30 verdicts.
*Why:* enough items to separate the arms without overkill. *Tradeoff:* about 180 generator
requests per full run of 500 per day; partly self-graded until owner review.

**D49. Rerank the vector top 10 with the decision model.** Owner-approved on 2026-11-16.
Retrieval becomes two stages: vector search returns 10 candidates, then gemini-decision-1
answers one yes/no question per candidate ("does this provision help answer the question?")
in a single request, and candidates are ordered by P(yes), ties kept in vector order. The
assistant keeps the top 5. Basis: in the raw R7 and R8 rankings the gold paragraph is in the
vector top 10 for all 95 questions, so the 11 rank-1 misses are ordering errors. The reranker
is measured against vector alone on the dev split with the paired bootstrap (D48), then
confirmed once on a test split.
*Why:* the standard retrieve-then-rerank pattern, aimed at the measured failure. *Tradeoff:*
one extra decision request per question (10,000 per day free), more latency, and the gain is
capped at the 11 misses, so it may not reach significance on the current sets.

**D50. A reranker failure degrades `ask` to vector order; evals stop instead.** Decided by the
builder on 2026-11-16 under the owner's go-ahead for D49. If the decision call fails (provider
error, quota or budget), `niyam ask` keeps the vector top 5 and the reply says reranking
failed; `eval-pipeline` exits with the error so no score mixes reranked and unreranked replies.
*Why:* a student still gets the computed deadlines, which never depend on retrieval order.
*Tradeoff:* a degraded reply may cite less relevant provisions; the note makes that visible.

**D51. The H-1B cap-gap rules of 214.2(f) are in scope.** Owner-approved on 2026-11-16. A
student whose employer filed a cap-subject H-1B change-of-status petition is answered from
8 CFR 214.2(f)(5)(vii): status and OPT work authorisation extend to April 1 of the fiscal year
or the petition's validity start date, whichever is earlier, and end on rejection, denial,
revocation or withdrawal, or when change of status is denied (consular processing). The rules
engine will compute the extension end date; "H-1B" leaves the not-covered list, which keeps the
lottery, specialty-occupation rules and the petition itself (8 CFR 214.2(h), not indexed).
*Why:* the indexed regulation answers it, and it is a deadline students get wrong. *Tradeoff:*
the departure period after a terminated extension is not stated in (f)(5)(vii); SEVP's page
says 60 days but predates the 2026 rule that set (f)(5)(v) to 30, so the reply must flag it.

**D52. Only qualifying jobs stop the unemployment clock.** Owner-approved on 2026-11-16.
Supersedes convention (2) of D44. A job counts as employment only if it is directly related to
the major (8 CFR 214.2(f)(10)(ii)(A)) and, during a STEM extension, at least 20 hours a week
((f)(10)(ii)(C)(8)); regular OPT has no hours minimum in the text. A job the student calls
unrelated counts as unemployment. When the student did not say, the job is counted, the
assumption is shown on the finding, and the missing fact is asked for. Basis: a fact-check
against official sources found no support for "every job counts".
*Why:* the old convention under-counted unemployment for students in unrelated jobs, which is
the costly direction. *Tradeoff:* more follow-up questions; "related to the major" is the
student's own judgement, not something code can verify.

**D53. After a cap-gap extension ends, give the cautious 30-day departure date and flag it.**
Decided by the builder on 2026-11-16 at the owner's request to resolve the conflict. 8 CFR
214.2(f)(5)(vii) does not state a departure period after termination. SEVP's cap-gap page
(last updated 2025-04-10) says 60 days from the later of termination and the program or OPT end
date; the 2026-07-17 final rule (FR Doc 2026-14439, effective 2026-09-15) cut (f)(5)(v) to 30
days and, in the excerpts found, does not address cap-gap. Niyam gives 30 days after the later
of the petition decision and the OPT end, cites (f)(5)(v), and states the conflict. A consular-
processing petition gets no extension; a pending or approved change-of-status petition replaces
the ordinary departure finding with the extension end date.
*Why:* leaving early costs less than overstaying. *Tradeoff:* students may plan for 30 days
when DHS would allow 60; the reply says so and points to the DSO.

**D54. Independent eval sets are scored against their own hand-derived gold.** Decided by the
builder on 2026-11-16 under the owner's go-ahead for step 5. The sets in evals/independent/
were written by an agent that never saw this codebase (owner's request), from the regulation
only. `eval-edge` scores the full reply the student sees: code checks every expected deadline
date and day count against the computed findings, asking when facts are missing, citing a gold
paragraph, declining out-of-scope parts, and (security cases only) literal leaks such as an
echoed SSN; the judge checks only the must-say and must-not-say points. Results are reported
per category, per confidence and for ambiguous cases separately. Unlike the pipeline eval, gold
deadlines never come from our own rules engine.
*Why:* removes the builder grading its own homework. *Tradeoff:* the gold is still model-
written until the owner's review; about 3 to 4 model requests per case.

**D55. Retry temporary provider errors three times and count every attempt against quota.**
Owner-approved on 2026-11-19. A Gemini 503 ("high demand") from the judge stopped eval-edge
after about 6 cases. Two causes: retries defaulted to 0, and the generator and judge use the
interactions API, whose errors (google.genai._gaos compat_errors) are not the errors.APIError
our adapter translated, so even a 429 there crashed. Now a 429 is a rate limit, any 5xx is a
temporary provider failure, and both are retried up to 3 times with 2, 4 and 8 second waits.
Google's troubleshooting page names 429 and 503 as retryable and says to retry 5xx. Every
rejected attempt is recorded in the ledger as a request, because the page does not say
whether failed requests count against quota.
*Why:* long eval runs on free-tier models die on short provider spikes. *Tradeoff:* a run can
wait about 14 seconds per failing call; the ledger may over-count requests on bad days.

**D56. Retry malformed judge output twice, then report the case as a judge failure.**
Owner-approved on 2026-11-19. With D55 in place, eval-edge stopped again at about case 9:
gemma-4-31b-it returned JSON that did not parse as RubricVerdict. Both judges (answer and
rubric) now try up to 3 times; only parsed outputs are cached, so each retry is a fresh request,
and the meter now records an unusable response as a request. If all 3 tries fail, eval-edge
keeps going: the case gets judge_failed, is left out of every pass rate, and the summary counts
judge failures per group.
*Why:* one malformed judge reply should not throw away a whole run. *Tradeoff:* a judge
failure is not a fail, so a judge that fails often could flatter the pass rate; the count is
reported next to it, and frequent failures mean replacing the judge.

**D57. The corpus stays 8 CFR 214.2(f); 214.2(h) is not added.** Owner-approved on 2026-11-19.
Reaffirms D51 after weighing expansion: 214.2(h) is about 3 times the text of (f) (583 vs 181
XML paragraphs) and the parser cannot yet tell paragraph (i) from roman (i). The independent
H-1B set cites 214.2(h) in 61 of its 70 cases and expects full answers there, which our scope
declines. It is not scored until the owner has marked those cases on the gold review page and
their gold is rewritten to expect a decline.
*Why:* a narrow assistant that knows its limits is more reliable than a broad one that
guesses. *Tradeoff:* H-1B questions beyond cap-gap get a referral, not an answer.

**D58. Rules-engine, guardrail, and scope bug fixes from the gold audit.** Owner-approved on
2026-11-19. Four code changes: (1) `StudentFacts.jobs` becomes `list[Job] | None = None` so
unmentioned employment asks instead of falsely computing `over_limit` unemployment, while
`jobs=[]` still represents explicit unemployment; (2) `OutOfScope` narrows `"travel, visa
stamping or re-entry"` to `"visa stamping or consular renewal"`, because 8 CFR 214.2(f)(4) and
(f)(13) are indexed and cover F-1/OPT re-entry documents; (3) `check_explanation()` allows dates
quoted verbatim from the given regulation provisions (e.g. "April 1", "September 15, 2026", and
their ISO equivalents) while still rejecting altered years or ungrounded dates; (4) `opt.py` and
`dates.py` fix the STEM-without-`opt_end_date` crash, year-boundary observed New Year's Day
(`2027-12-31`), inverted OPT dates, program-end departure period, and duplicate departure
findings after terminated cap-gap.
*Why:* these were live crashes, false guardrails, and scope contradictions uncovered before
running the full offline evals. *Tradeoff:* changing `StudentFacts.jobs` and the extraction
prompt invalidates cached extraction responses, so the next eval run makes fresh extraction
calls.

**D59. Eval scorer and P0 gold-set fixes.** Owner-approved on 2026-11-19. In `edge.py`: separate
mechanical leak checks (`forbidden_literals`) from semantic `must_not_say` rubric points so safe
refusals do not trip on ordinary words ("Yes.", "E-Verify number", "60 days"); add
`any_deadline` for mutually exclusive convention alternatives; make `_count_stated` distinguish
"used" from "remaining"/"left"; require `scope="in"` replies not to be flagged `out_of_scope`;
and skip `cites_gold` on `scope="out"` declines. In `extraction.py`: include `related_to_major`,
`hours_per_week`, and `None` vs `[]` when scoring `jobs`. Fixed verified P0 gold bugs in
`retrieval-dev.jsonl` (`d16`, `d22`, `d26`, `d30`, `d34`, `d35`, `d51`, `d58`),
`retrieval-test.jsonl` (`r05`, `r14`, `r19`, `r28`), `extraction.jsonl` (`e07`),
`pipeline.jsonl` (`p05`, `p08`, `p19`, `p24`, `p27`, `p33`), `edge_cases.jsonl` (`x010`, `x018`,
`x040`, `x047`, `x052`, `x054`, `x068`, `x069`, `x081`, `x084`), and `decline_and_security.jsonl`
(`y020`, `y024`–`y040`).
`h1b_cases.jsonl` stays untouched per D57.
*Why:* scorer and gold bugs caused both false failures and false passes that would corrupt eval
numbers. *Tradeoff:* editing 4 gold lists in `retrieval-test.jsonl` (adding missing valid
paragraphs only) means future test retrieval scores are not strictly comparable to R4/R8 without
noting the added alternatives.

**D60. Rewrite docs/PROJECT_CONTEXT.md for the F-1 product.** Owner-approved on 2026-11-19. The
file still described the abandoned RBI/NPCI project, so the phase-start reading rule in
CLAUDE.md pointed at the wrong content. It now describes the F-1 work-rules assistant over
8 CFR 214.2(f) (D42, D51, D57), keeps the 17-section numbering (section 4 Hard constraints,
section 11 Phases), cites only existing R-entries, and states that DECISIONS.md wins on
conflict. Facts it could not source (web framework, hosting, Phase 4 spec) are marked
to-verify, not guessed. The draft was fact-checked against the logs and providers.md by a
read-only subagent, and its errors were fixed before commit.
*Why:* a stale source of truth misleads every new phase. *Tradeoff:* the doc is a snapshot and
will drift again unless updated at phase starts.

**D60b. Separate retrieval `gold` from answer-eval `context` and fix remaining D59 audit findings.**
Owner-approved on 2026-11-19. Amends D59 for `d22`, `d26`, `d34`, `x054`, `p24`, and `y031`:
(1) `AnswerItem` in `src/niyam/evals/answers.py` now reads an optional `context` list so
`eval-answers` receives parent/child provisions (`d22`: `(C)(10)`, `d26`: `(f)(4)(i)-(ii)`,
`d34`: `(f)(5)(vii)(A)(1)-(3)`) while `eval-retrieval` keeps strict single-rule `gold` (no bare
fragments satisfying any-of `hit@k`); (2) removed bare fragments `(A)(1)-(3)` from `x054`
`gold_paragraphs`; (3) added `8 CFR 214.2(f)(17)` alongside `(f)(12)(ii)(A)` on `p24`;
(4) rephrased `"E-Verify number"` in `y031` `must_not_say` to
`"Provides a fabricated E-Verify number"` so safe refusals quoting `(f)(10)(ii)(C)(5)` do not
trip the rubric judge.
*Why:* putting lead-in stems or child fragments in retrieval `gold` inflates any-of `hit@k`,
whereas omitting them from `eval-answers` hides facts the reference answer requires. *Tradeoff:*
one extra optional field in `retrieval-dev.jsonl`.

**D61. Align `evals/independent/h1b_cases.jsonl` gold labels with D57 scope (8 CFR 214.2(f) only).**
Owner-approved on 2026-11-19. Reclassified the 70 independent H-1B cases from 55 `in` / 9 `partial`
/ 6 `out` to 11 `in` (`h031`–`h038`, `h044`, `h049`, `h061`), 6 `partial` (`h018`, `h024`, `h039`,
`h058`, `h060`, `h062`), and 53 `out` (all `214.2(h)` / non-corpus cases plus cleaned-up existing
`out` rows). Rewritten `out` rows follow `decline_and_security.jsonl` conventions (empty
`gold_paragraphs`, `expected_deadlines`, `expected_counts`; polite decline + referral in
`must_say`; no substantive `214.2(h)` claims in `must_not_say`; `forbidden_literals` kept on
prompt-injection case `h068`). Stripped non-corpus citations (`214.2(h)`, `214.1(m)(1)`, `248.1`)
from `in`/`partial` rows, aligned `h049` with D53, and added `any_deadline: true` on `h031`,
`h032`, `h036`, and `h061`.
*Why:* per D57, H-1B rules outside 8 CFR 214.2(f) cap-gap must be declined rather than answered.
*Tradeoff:* the 53 rewritten cases now test refusal/referral quality rather than H-1B rule recall.

**D62. Open read-only CLI and eval Postgres connections in autocommit mode and log eval progress.**
Owner-approved on 2026-11-19. Added `autocommit: bool = False` to `_connect()` in
`src/niyam/cli.py` and passed `autocommit=True` from read-only commands (`eval-edge`,
`eval-pipeline`, `eval-retrieval`, `search`, `ask`) while keeping `index` transactional
(`autocommit=False`). Also added per-case stderr progress lines (`[i/N] <id> ...`) to
`eval-edge` and `eval-pipeline`.
*Why:* without autocommit, the first retrieval query opened a transaction that stayed idle across
slow generator/judge calls until Neon's `idle_in_transaction_session_timeout` killed the run after
~36 minutes. *Tradeoff:* none for read-only queries; progress lines go to stderr so stdout stays
clean.


**D63. Scope eval Postgres connections per case and close before judging.**
Owner-approved on 2026-11-19. Amends D62 for `_eval_edge` and `_eval_pipeline` in
`src/niyam/cli.py`: `with _connect(autocommit=True) as conn:` now wraps only
`_strict_answer(...)` inside each per-case iteration instead of spanning the whole eval loop
and the judge step.
*Why:* even with `autocommit=True`, Neon closes idle SSL connections after ~5 minutes, so any
single case where `gemma-4-31b-it` retries took >300s dropped the connection and crashed the
next case's retrieval query. *Tradeoff:* one short connection handshake per eval case.

**D64. Phase 4 plan: TypeScript web app over a hardened, streaming FastAPI endpoint.**
Owner-approved on 2026-11-20. Phase 4 runs as 4a harden the API, 4b TypeScript frontend,
4c Langfuse tracing, 4d deploy to free hosts, 4e README and owner gate. The frontend is
Vite + React + TypeScript (strict) in `web/`, replacing the untracked JavaScript scaffold. 4a:
`pipeline.answer` reports each stage (`extract`, `rules`, `retrieve`, `rerank`, `explain`,
`verify`) with its duration through an optional callback, so the CLI and the API share one
orchestration; `POST /api/ask` streams those stages and then the reply as server-sent events;
requests are limited per client IP per hour and by a global per-quota-day cap
(`DEMO_DAILY_CAP`, default 150 asks, leaving generator headroom for evals); provider quota and
overload errors reach the browser as a generic "busy" message and any other error as a generic
internal error (details only in server logs); CORS origins come from `CORS_ORIGINS`.
*Why:* the free generator allows about 250 asks a day, so an unlimited public endpoint could
exhaust the quota; streaming lets the page animate real pipeline progress instead of a timer.
*Tradeoff:* limits are in-process memory, so they reset on restart and assume one instance;
client IP is only correct behind a proxy if uvicorn runs with `--proxy-headers` (set in 4d).

**D65. Deploy publicly before the remaining evals finish; build Phase 4 in parallel.**
Owner-approved on 2026-11-20. Amends the Phase 4 gate in `docs/PROJECT_CONTEXT.md` section 11:
the app may go live on a public URL while `eval-edge` (edge_cases), `eval-pipeline` and
`eval-answers` are still running or unrun; the README states which results are pending. 4b
(website), 4c (Langfuse) and 4d (deploy prep) run in parallel sessions; their decisions take
D66 (4b), D67 (4c) and D68 (4d) so the numbering does not collide.
*Why:* nothing in the app depends on eval results, the project has no real users yet, and the
evals are bound by free-tier judge speed and generator quota. *Tradeoff:* the public page may
show an assistant whose measured scores are incomplete; the disclaimer and the daily cap
(D64) still apply, and public traffic shares the generator quota with the evals.

**D66. TypeScript website in `web/` with a recorded-answer replay.**
Owner-approved on 2026-11-20 (Phase 4b under D64/D65). `web/` is Vite + React 19 + TypeScript
(strict, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`) with Motion for animation
and self-hosted Fraunces/Inter fonts; no CSS framework. The page streams `POST /api/ask` and
lights up each real pipeline stage as its event arrives, then shows the answer with clickable
citations, a date timeline of the findings, finding cards, the facts it understood, missing
facts, the quoted source paragraphs, the disclaimer and the corpus snapshot date (served by
`GET /api/health` from `data/manifest.json`). "Watch a recorded answer" replays one real
reply captured from the live pipeline (`web/src/fixtures/`), labelled as a recording, with its
measured stage times at 4x speed. Animations respect `prefers-reduced-motion`; light and dark
themes follow the system.
*Why:* the replay lets visitors and development use the page without spending the shared free
generator quota, and stays usable when the daily cap is reached. *Tradeoff:* the recorded
reply can drift from current pipeline output; re-record it when prompts or rules change.

**D67. Trace each answer to Langfuse: one trace, a span per stage, three scores, fail-safe.**
Owner-approved on 2026-11-20 (Phase 4c under D64/D65; built in a parallel session).
`pipeline.answer` opens one trace (root observation `answer`) through a `Tracer` carried in
`Services`; `_StageTimer` wraps each of `extract`, `rules`, `retrieve`, `rerank`, `explain`,
`verify` in a child span, so tracing reuses the D64 orchestration. Each trace is scored with
`withheld` and `rerank_failed` (boolean) and `findings` (count). Only the restated question and
`as_of` are sent as input, never the student's message: neither section 10 nor any D-entry
allows sending it, and the restated question already omits identifiers. Failed stages send
only the error type name. `niyam ask` and the web API trace when `LANGFUSE_TRACING` is true
(default); evals build `Services` without a tracer and never trace. `build_tracer` calls
`auth_check()` once at startup and falls back to no tracing, logged once, if Langfuse is
unreachable or rejects the keys; any later SDK exception switches tracing off for the process,
also logged once. Answers never call `flush()`; the SDK exports in a background thread.
*Why:* section 10 asks for per-stage spans and scores; measured SDK behaviour (docs/providers.md)
shows `flush()` blocks for seconds and `auth_check()` raises when Langfuse is down, so neither
may run per answer. *Tradeoff:* if Langfuse is down at startup, tracing stays off until restart;
if it goes down later, the SDK's own exporter logs a failure per batch (not once), which we do
not suppress. By the docs' unit definition each answer costs 11 units (1 trace, 7
observations, 3 scores), so 150 asks a day (the D64 cap) for 30 days is 49,500 units, just under
the Hobby plan's 50,000; tracing evals as well would exceed it.

**D68. Phase 4d deploy prep: Docker image, CI, and a recommended free host pairing.**
Requested by the owner's Phase 4 plan (D64, D65) on 2026-11-20; the host itself stays the
owner's open decision (`docs/PROJECT_CONTEXT.md` section 13). A two-stage `Dockerfile` installs
the locked, non-dev dependencies with `uv` 0.13.8 on `python:3.12-slim` and runs
`uvicorn niyam.api:create_app --factory --proxy-headers` as a non-root user; all settings come
from environment variables and `.dockerignore` keeps `.env`, `.state`, `.tools`, data, results
and `web/` out of the build. `FORWARDED_ALLOW_IPS` defaults to private ranges because uvicorn
takes the left-most `X-Forwarded-For` entry when trusting `*`, which a client can spoof.
`.github/workflows/ci.yml` runs ruff, ruff format, mypy and pytest via `scripts/bootstrap.sh`,
plus a `web` job that is skipped until `web/package.json` exists. Recommended: API on Render
free (Docker), website on Cloudflare Pages; runbook in `docs/deploy.md`.
*Why:* Render free needs no card, allows outbound Postgres on 5432 and long HTTP requests;
Hugging Face Spaces block outbound ports other than 80, 443 and 8080 (no Neon over psycopg),
Cloud Run needs a billing account with a card, and Koyeb asks for a card and caps HTTP
requests at 120 s. *Tradeoff:* Render free sleeps after 15 idle minutes (about a minute to
wake) and has no persistent disk, so the response cache, quota ledger and in-memory ask limits
reset on every restart.

**D69. Host the site and API together on Vercel; build, test and publish the container in CI.**
Owner-approved on 2026-11-21. Supersedes D68's recommendation of Render and Cloudflare Pages
(the Dockerfile, CI and runbook from D68 stay). One Vercel Hobby project serves the website as
static files from `public/` (built from `web/`) and the FastAPI app as a Python function at
`/api/*`, so the site and API share one origin and need no CORS. Production details:
`STATE_DIR` is `/tmp` (the only writable path); the per-IP limit reads the client address from
`CLIENT_IP_HEADER=x-real-ip`, which Vercel overwrites with the real client IP so it cannot be
spoofed; Langfuse is flushed after the reply event and before the stream closes, because a
serverless instance may be frozen once the response ends. CI builds the Docker image on every
push, starts it and checks `GET /api/health`, and on `main` publishes it to GitHub Container
Registry as `ghcr.io/algo-ankit/niyam-api` (tags: commit SHA and `latest`).
*Why:* Render's free API sleeps after 15 idle minutes and takes about a minute to wake, which a
visitor to a portfolio link will not wait for; Vercel serves the page instantly and starts the
API in seconds, on an account the owner already has. The published container keeps the API
portable to any container host. *Tradeoff:* ask limits and the response cache are per instance
and reset when instances recycle, so they are approximate; Gemini's own free-tier quota remains
the hard stop. Hobby is for personal, non-commercial use, which this project is.

**D70. Deploy on Vercel as two Services, `api` and `web`.**
Owner-approved on 2026-11-21. Supersedes the `public/` build step in D69 (the rest of D69
stands). Vercel's importer detects the FastAPI app and the Vite site and requires the
multi-service form of `vercel.json`: service `api` (root `.`, FastAPI, entrypoint
`niyam.asgi:app`, 60 s `maxDuration`, dev and data folders excluded from the bundle) and
service `web` (root `web`, Vite). Both are public: `/api/*` routes to `api`, everything else to
`web`, on one domain. No service bindings: only the visitor's browser calls the API, and it
uses the same origin.
*Why:* it is the platform's supported layout for a frontend plus backend in one project; each
service is built by its own framework preset instead of copying the site into the API's
`public/` folder. *Tradeoff:* Services is a newer Vercel feature, so the first deploy is the
real check of this configuration.

**D71. End an ask with "busy" after a 50-second deadline instead of letting the host cut it.**
Owner-approved on 2026-11-21 (fix found in the first live Vercel test). `POST /api/ask` now ends
the stream with the generic "busy" error if no reply or error has arrived within
`ASK_DEADLINE_SECONDS` (default 50), which must stay below the host's request limit (Vercel
`maxDuration` 60 s). An ask that already sent its reply is never followed by "busy".
*Why:* in the first production ask, Gemini answered `503` twice, each after about 30 s, and the
D55 retries ran past Vercel's 60 s limit; the platform killed the function and the visitor got an
empty stream with no message. *Tradeoff:* an answer that would have finished between 50 s and
the retry budget is reported as busy; the visitor can retry, and cached steps replay free.

**D73. Give each answer-model call a 15-second timeout, retried like a 503.**
Owner-approved on 2026-11-21. The generator's Interactions call is sent with
`timeout=GENERATION_TIMEOUT_SECONDS` (default 15 s). A timeout is raised as
`ProviderUnavailableError`, so the D55 retries treat it like a 503. The judge (evals only) and
the decision and embedding calls keep no timeout. Verified live on 2026-11-21 with
google-genai 3.3.0: `interactions.create(timeout=0.3)` raised
`compat_errors.APITimeoutError` after 0.4 s; with 20 s a short prompt answered in 8.9 s.
*Why:* in production, each Gemini 503 took about 30 s to arrive, so one failed call used most
of the 50 s ask deadline (D71) and no retry could finish. With 15 s, a slow or failing call is
abandoned early and up to two more attempts fit inside the deadline. *Tradeoff:* a generator
call that would have succeeded after 15 s is cut and retried; the locally measured 8.9 s for a
tiny prompt shows headroom is not large, so the value is a setting and is checked again in the
live test.

**D72. Route greetings and unrelated messages away from the legal pipeline.**
Owner-approved on 2026-11-21. The extraction step also labels the message's `kind`: `question`
(anything about studying or working in the US on a student visa), `greeting` (hello, thanks,
or a question about the assistant itself) or `unrelated` (nothing to do with that). A
`greeting` or `unrelated` message that states no facts gets a fixed, builder-written reply
(what Niyam covers, with example questions) and skips rules, retrieval, rerank, explain and
verify. Any message with a stated fact always takes the full pipeline. The reply carries
`kind`, and the site shows non-question replies as one plain card.
*Why:* in the live site "hello, what can you do" ran all six stages and about five model calls
and came back as a regulation answer with sources. The guardrails (rules-engine dates,
checked citations) stay for every real question, because they are what make an answer safe to
act on. *Tradeoff:* a mislabelled real question with no facts gets the capability reply; the
student can rephrase. The reply text is fixed, not model-written, so it cannot overclaim.

**D74. Raise the per-IP limit to 60 asks an hour, and make refusals and waiting visible.**
Owner-approved on 2026-11-21. Amends D64's per-IP default (10 to 60); the daily cap (150) and
the 50 s ask deadline (D71) are unchanged. On the site: an ask refused before any stage starts
(hourly or daily limit) hides the pipeline card and shows one card with a live countdown to
the next allowed ask, and the Ask button stays disabled with the same countdown. While an
answer runs, the elapsed time is shown large, and after 15 s a line says the model is slow,
it is still working, and it stops at 50 s; a stopped or busy ask offers Try again.
*Why:* the site serves 4 to 5 people; at 10 an hour, one owner test locked the owner's own
network out, and the refusal showed only as an empty pipeline card marked "Stopped". 60 an
hour is never reached by a person but still stops a script before it drains the shared free
Gemini quota for everyone. *Tradeoff:* the limit is keyed on the public IP, so everyone behind
one network (home wifi, an office) shares one 60; counts stay per server instance (D69). A
login-based limit is planned later.
