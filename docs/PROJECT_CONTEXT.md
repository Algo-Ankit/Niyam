# Niyam: Project Context

Working name: **Niyam** (Hindi for "rule"), package name `niyam` (D18).

This file describes what we are building, why, how, and in what order. Read it by section, not in full (D29). If a later instruction from the owner conflicts with it, the owner wins and the change is recorded in `DECISIONS.md`. Where this file and `DECISIONS.md` disagree, `DECISIONS.md` wins.

The current product is set by D42 (2026-11-15). Measured numbers live in `RESULTS.md` (cited as R#N).

---

## 1. What we are building

**One line:** an F-1 student work-rules assistant for OPT, STEM OPT and H-1B cap-gap, built on 8 CFR 214.2(f), with staged evaluation and monitoring (D42, D51).

**Who it is for.** F-1 students who need to know which rules apply to them and by when, in plain words, with the regulation paragraph cited.

**Input.** The student's situation in plain words: program end date, OPT or STEM OPT dates, employment and gaps, degree, and whether an employer filed a cap-subject H-1B petition.

**Output, always the same shape (D42, D46):**
- Findings: each rule that applies, its paragraph cited, the computed date or count, and a status.
- The student's deadlines as dates, and unemployment days used against the limit.
- Assumptions the code applied where the regulation is silent (D44).
- Missing facts: what the assistant asks for instead of guessing.
- A model-written explanation, shown only if it passes the code checks (D46).
- A "not covered" list and the disclaimer, rendered by code.

**Core design rule.** The model extracts facts and writes the explanation; deterministic code computes every date and day count; retrieval supplies the cited text; code checks the model's output before anyone sees it (D42, D46).

**Example questions it should answer**
- When must I file for post-completion OPT, and what is my latest start date?
- How many unemployment days have I used, and how many do I have left?
- My employer filed an H-1B petition. How long does my work authorisation extend (cap-gap)?
- What must I report during my STEM OPT extension?

**Out of scope, declined and referred to the DSO or a lawyer (D42, D51, D58):** H-1B beyond cap-gap (lottery, specialty occupation, the petition itself, 8 CFR 214.2(h)), green card, taxes, visa stamping or consular renewal, other statuses, anything needing the DSO or a lawyer.

### Non-goals (v1)
- Not legal advice; it says so on every answer.
- One message, one answer. No conversation history.
- No user accounts, billing, or uploads.
- No automatic re-crawling. The corpus is a dated snapshot.
- 8 CFR 214.2(h) is not indexed and is not added for now (D57).

**Scope discipline.** Do not add features, services, or phases that are not in this file or `DECISIONS.md`. If something seems missing, raise it in a briefing.

---

## 2. Why this project exists (optimise for this)

A specific user with a costly problem (loss of status), no free tool that does the date arithmetic, and verified official sources (D42). The owner is an AI engineer building a portfolio project; it must show, with real evidence:

1. A retrieval pipeline with measured comparisons between approaches (R4, R7, R8, R9).
2. A decision model used for re-ranking (D21, D49).
3. Guardrails: the model never produces a date; code checks its output; the assistant asks or declines instead of guessing.
4. Staged offline evaluation: extraction, rules engine, retrieval, answers, whole pipeline, adversarial and independent sets (D48, D54).
5. Monitoring with Langfuse and a CI regression gate (not built yet).

Consequences:
- **Measured numbers only.** Never write a metric into the README, docs, or commit messages without a `RESULTS.md` entry.
- **Honest results.** If the simple approach beats the fancy one, report that (D47).
- **Simple and legible beats clever.** The owner must be able to explain every part.

---

## 3. Roles and working agreement

**Owner (human): architect and decision maker.** Sets goals, approves plans, makes tradeoff decisions, reads results, reviews gold sets, and labels a sample of judge verdicts.

**Claude Code: builder.** Collects documents, writes code and tests, runs evaluations, and briefs the owner. The workflow rules in `CLAUDE.md` apply.

### Process for every phase
1. **Plan:** a short plan (what, which files, how verified, open questions). Wait for approval.
2. **Build** in small commits, one logical change each, with its `DECISIONS.md` entry in the same commit.
3. **Verify:** run the full suite and the phase's acceptance checks; show real output.
4. **Brief:** at most one page: what was built, what was found, numbers and their `RESULTS.md` entries, problems, decisions needed.
5. **Stop at the gate** until the owner approves.

### Standing rules
- **Decisions log:** every non-trivial choice goes in `DECISIONS.md` (decision, why, tradeoff). Append-only.
- **Money:** the decision model is set by `DECISION_PROVIDER`. Never spend money or exceed `DECISION_BUDGET_USD` without owner approval.
- **Isolated environment, no global changes.** The toolchain is repo-local (`.tools/`, `.venv`, created by `scripts/bootstrap.sh`; D11). No global installs, PATH or profile edits, or global git config.
- **Secrets:** only in `.env` (gitignored) and GitHub Actions secrets. Never print or commit them.
- **Verify providers before coding against them** (section 5): current docs plus one live call; findings in `docs/providers.md`.
- **Sources:** official government text only (D38). Never print whole regulations or large datasets.
- **Teach:** in each briefing, explain new concepts in two or three plain sentences and say what the owner should be able to explain back.
- If something behaves differently from expected, stop and report. Do not work around it silently.

---

## 4. Hard constraints

| Constraint | Detail |
|---|---|
| Budget | Free tiers everywhere (D35, D36). Any spend needs owner approval; decision-model spend is capped by `DECISION_BUDGET_USD` and enforced in code by a spend ledger. |
| Decision model | `gemini-decision-1` on the Gemini key, free tier (D21): the reranker (D49). Limits: 200 RPM, 50K TPM, 10K RPD (D34). |
| Generative model | `gemini-3.5-flash-lite`, free tier (D35): fact extraction and explanation. Limits: 15 RPM, 250K TPM, 500 RPD. |
| Judge | `gemma-4-31b-it` (D36): a different family from the generator. Limits: 30 RPM, 16K TPM, 14,400 RPD. Uncalibrated until the owner labels about 30 verdicts (D48). |
| Embeddings | `gemini-embedding-2`, 768 dimensions (D24). Limits: 100 RPM, 30K TPM, 1K RPD; each text in a batch is assumed to count as one request (D34, D45; unverified in docs/providers.md). |
| Provider errors | 429 and 5xx retried 3 times (2, 4, 8 s) with every attempt counted against quota (D55); malformed judge output retried twice, then reported as a judge failure (D56). |
| No local model inference | No local LLMs or GPU. |
| Data | Official government text only (D38): 8 CFR 214.2(f) from the govinfo bulk eCFR XML (D43). Processed text is committed (public domain, 17 U.S.C. 105); raw XML is gitignored. Download politely, only approved sources. |
| Dates and counts | Computed only by the rules engine, never by a model (D42, D46). |
| Caching | Our own response cache only; no provider-side context caching (D22). Cache hits never consume quota (D25). |
| Observability | Langfuse. |
| Stack | Python 3.12, google-genai (Gemini), langfuse, psycopg, pydantic-settings, Postgres (Neon) with pgvector, `uv`, ruff, `mypy --strict`, pytest. |

---

## 5. Providers: what is known and what to verify

Verified provider facts are in `docs/providers.md`. Summary of decisions:

- **Gemini API (free tier).** Generator, decision model, judge and embeddings all use the one Gemini key. Generation and judging use the Interactions API. The judge adapter sends `thinking_level` only when set, because Gemma rejects it (D36). Default thinking level is `low` (D23).
- **Rate limits** are shown only in Google AI Studio; owner-confirmed values are in section 4 (D34, D35, D36). `Meter` counts in-flight calls (D32).
- **Model stack** is composed as `Cached(Metered(Adapter))` (D25).
- **Postgres (Neon),** direct unpooled connection string (D20); pgvector 768-dimension column and a generated English tsvector (D45).
- **Langfuse:** check the current Python SDK and API against the docs and one live call before coding against it. Hobby (free) plan: 50,000 units a month, 30 days of data access (docs/providers.md); behaviour past 50,000 is not stated. On Langfuse Cloud the old `POST /api/public/ingestion` endpoint accepts only scores from 2026-11-16; SDK v5 is based on OpenTelemetry and is expected to be unaffected, but the docs do not say so (an inference, unverified). Hobby is still free on the pricing page. Before Phase 4, send one real trace and confirm it arrives.
- **Decision model:** `gemini-decision-1` (D21); the `DecisionModel` interface stays provider-neutral.

**Design requirement:** every model sits behind an internal interface with provider adapters, a response cache, a rate limiter and a spend ledger, so a model can be swapped by one config value.

---

## 6. The knowledge base

- **Corpus v1: 8 CFR 214.2(f) only** (D43, D57). Source: govinfo bulk eCFR title 8, parsed into 203 provisions with citation path and headings; 181 provisions are indexed. The parser rejects any label that breaks the CFR numbering sequence. Heading-only provisions are not indexed; their headings lead each child's search text (D45).
- **Includes** the H-1B cap-gap rules of 214.2(f)(5)(vii) (D51). **Excludes** 8 CFR 214.2(h) (D57).
- **DHS Study in the States pages are deferred** until each page is checked against the current regulation; the regulation wins on conflict (D43, D38).
- **Reproducibility:** `niyam corpus-fetch` downloads the raw XML (SHA-256 in `data/manifest.json`); `niyam corpus-build` parses it; `niyam index` embeds and loads it into Postgres.
- **Freshness:** the corpus is a dated snapshot (title 8 current as of 2026-10-14). Immigration rules change (DHS proposed an OPT fee rule on 2026-10-08; a 2026-07-17 final rule set the (f)(5)(v) departure period to 30 days), so a freshness check is needed (D42, D53).
- **Retrieval:** vector search over the indexed provisions, then rerank of the top 10 by the decision model, keep the top 5 (D47, D49). Keyword and hybrid stay in the eval as comparison arms.

---

## 7. The test set

All eval sets are in `evals/` (JSONL). Gold is paragraph-anchored.

- **Retrieval:** a dev split for tuning and a held-out test split (`retrieval-dev.jsonl`, `retrieval-test.jsonl`); cap 190 questions (D48).
- **Extraction:** `extraction.jsonl`, labelled messages with gold facts and expected deadlines.
- **Answer quality:** questions with reference answers, judged by Gemma for correctness and grounding; cap 80 (D48). The set is not built yet and `eval-answers` has never run.
- **Pipeline:** scenarios in scope, out of scope and unanswerable; cap 80 (D48).
- **Independent sets** (`evals/independent/`): written by an agent that never saw this codebase, from the regulation only, with hand-derived gold (D54). They include edge cases, decline-and-security cases, and H-1B cases. The H-1B set is not scored until the owner has marked its 214.2(h) cases on the gold review page and their gold is rewritten to expect a decline (D57).
- **Gold review:** a private review page holds all 350 eval cases (every set, independent and builder-written) with regulation text; the owner's verdicts are stored in its database. Builder-written sets (retrieval, extraction, pipeline) have not had owner review. Gold fixes from audits are logged in D58 and D59.
- **Sizing rule (D48):** a set is doubled once, up to its fixed cap, only if the 95% paired-bootstrap interval on the comparison that matters includes zero.

---

## 8. Architecture

`niyam ask` runs this pipeline (D46, D49, D50):

1. **Extract** (generator): `StudentFacts`, a one-sentence question, and out-of-scope topics (fixed list). The student's message is untrusted input.
2. **Rules engine** (pure Python, `src/niyam/rules/`): findings with dates and counts, assumptions, and the missing facts it needs to ask for. Rules run only when their facts are known.
3. **Retrieve:** vector top 10, rerank with the decision model, keep 5; plus the paragraphs the findings cite.
4. **Explain** (generator), using only the given provisions.
5. **Output check** (code): withhold the explanation if it cites a provision it was not given, states an ISO date the rules engine did not compute, or writes a date in a form that cannot be checked. Dates quoted verbatim from the given provisions are allowed (D58).
6. **Render** findings, assumptions, missing facts, "not covered" and disclaimer by code.

If the reranker fails, `ask` degrades to vector order and says so; evals stop instead (D50).

### Rules engine conventions (D44, D52, D53)
Where the regulation is silent, conventions are shown to the user as assumptions on the finding they affect:
- Unemployment days count from the OPT EAD start date.
- Only qualifying jobs stop the unemployment clock: directly related to the major, and during STEM OPT at least 20 hours a week (D52). `jobs` is `None` when unmentioned (ask), and `[]` for explicit unemployment (D58).
- Business days exclude weekends and the 5 U.S.C. 6103 federal holidays, moved to the observed weekday.
- A 24-month STEM period starting on day D ends the day before the same date 24 months later.
- "Completion of study" for the 14-month limit is the program end date.
- After a cap-gap extension ends, give the cautious 30-day departure date, cite (f)(5)(v), and flag the conflict with SEVP's 60-day page (D53).

### Guard details
Findings and deadlines never depend on retrieval order or on the explanation. A withheld explanation still shows the computed findings (D46, D50).

### Abstention wording
When a topic is out of scope or facts are missing, the assistant says what it does not cover or what it needs, and refers the student to the DSO. It does not guess (D42, D46).

---

## 9. Evaluation

Every number cites a `RESULTS.md` entry; `docs/results.md` is generated by code from saved raw output (D27).

### 9.1 Retrieval
Arms: keyword, vector, hybrid (reciprocal rank fusion), HyDE, vector plus HyDE, and vector plus rerank (D45, D48, D49). Metrics: hit@1, hit@3, hit@5, MRR@10, with a 95% paired bootstrap against vector. Measured so far: R4 and R8 (vector is the best simple arm; hybrid is worse), R7 (dev split), R9 (rerank on the dev split). Rerank has not yet been confirmed on a test split (D49).

### 9.2 Extraction
Field accuracy, all-fields-correct, out-of-scope topics, and agreement of deadlines with gold facts (R5, R6). R6 is optimistic because the prompt was changed after reading R5 on the same set.

### 9.3 Answers and pipeline
`eval-answers` (judge: Gemma, given the gold provisions) and `eval-pipeline` (whole assistant) are built but have not been run.

### 9.4 Independent sets (`eval-edge`, D54)
Scores the full reply the student sees: code checks every expected deadline date and day count, asking when facts are missing, citing a gold paragraph, declining out-of-scope parts, and (security cases) literal leaks; the judge checks only must-say and must-not-say points. Reported per category, per confidence, and for ambiguous cases separately. A case the judge cannot score is `judge_failed`, left out of pass rates and counted (D56). The scorer fixes are in D59.

### 9.5 Validating the judge
The owner labels about 30 verdicts and agreement is reported (D48). Until then judge scores are uncalibrated.

### 9.6 Reporting
Every number with its confidence interval and the command that produced it, from raw files in `results/`. Error analysis groups failures into causes (retrieval miss, ordering error, extraction error, rules-engine convention, over-abstention) with counts.

### 9.7 CI gate
Not built yet. Planned: ruff, mypy, tests, then metrics from cached responses with thresholds that fail the build on regression.

### 9.8 Quota awareness
Generator: 500 requests per day, about 2 per pipeline question and about 3 to 4 per `eval-edge` case (D46, D54). Judge: about 4 calls per minute in practice, sometimes overloaded or malformed. A crashed eval loses only its report; the response cache replays finished calls free, so rerun the same command.

---

## 10. Observability

Not built yet (Phase 4). Intended: Langfuse tracing with one trace per question and spans for extraction, rules engine, retrieval, rerank, explanation and output check, plus scores on each trace (for example whether the explanation was withheld); online evaluation on a sample of live answers; a spend ledger per provider; a status endpoint; and a feedback export for review. Langfuse plan limits must be verified before coding (section 5).

---

## 11. Phases

Each phase has a deliverable, acceptance checks and an owner gate. Status is from `HANDOVER.md` and `DECISIONS.md`.

### Phase 0: Setup and provider verification (done)
- Repo scaffold (`uv`, ruff, `mypy --strict`, pytest, git hook, `.env.example`, MIT license, `CLAUDE.md`, `DECISIONS.md`).
- One verified live call per provider; findings in `docs/providers.md`.
- Model interfaces, adapters, response cache, rate limiter, spend ledger.
- **Accept:** `uv run niyam verify-providers` passes.

### Phase 1: Corpus and rules (done)
- Downloader, eCFR parser, corpus build, Postgres index (D43, D45).
- Rules engine for OPT, STEM OPT and cap-gap deadlines (D44, D51, D52, D53).
- **Accept:** corpus matches the regulation text; rules covered by pytest derived from the regulation.

### Phase 2: Retrieval (done through rerank)
- Vector, keyword, hybrid, HyDE and rerank arms; dev and test splits (D47, D48, D49).
- **Accept:** reproducible with one command; intervals reported (R4, R7, R8, R9).
- **Open:** confirm rerank once on a test split.

### Phase 3: Answering, guards and evaluation (in progress)
- `niyam ask` pipeline with code-checked output (D46, D50).
- Eval sets: extraction, answers, pipeline, and the independent sets (D48, D54).
- Gold audits and fixes (D58, D59); owner review of gold; relabel the H-1B cases that cite 214.2(h) to expect a decline (D57).
- **Remaining:** finish `eval-edge` runs, run `eval-answers` and `eval-pipeline`, calibrate the judge with owner labels, error analysis, generate `docs/results.md`.
- **Gate:** owner reviews gold and failures.

### Phase 4: App, monitoring, CI, deploy (not started)
- Web page and endpoint with the disclaimer and snapshot date; rate limiting and a daily cap.
- Langfuse tracing, scores and online evaluation.
- CI with the eval gate; deployment to a free host.
- README with measured results and limitations.
- **Gate:** owner reviews the live demo and README before it is shared.

---

## 12. Decisions already made

The authoritative list is `DECISIONS.md` (D1 to D59, append-only). The ones that define the current project:
- D42: the product (F-1 student work-rules assistant); D38: official government text only.
- D43, D57: corpus is 8 CFR 214.2(f) only; D51: cap-gap in scope.
- D44, D52, D53: rules-engine conventions.
- D46, D50: pipeline and degradation behaviour; D47, D49: retrieval.
- D21, D35, D36: decision model, generator, judge; D24: embeddings.
- D48, D54, D56, D58, D59: evaluation design and fixes. D55: provider retry logic.

## 13. Open decisions for the owner
- Free hosting provider for the deployment.
- Whether and when to add checked Study in the States pages (D43).
- Whether to raise the generator tier if evals show the free model is not good enough (D35).

## 14. Known limitations to state openly
- Only 8 CFR 214.2(f) is indexed; H-1B questions beyond cap-gap get a referral (D57).
- The corpus is a dated snapshot, and immigration rules change.
- Some rules-engine conventions (for example when unemployment days start counting) may differ from SEVIS or USCIS practice in edge cases (D44).
- The cap-gap departure period conflicts between SEVP's page and the 2026 rule; the assistant gives the cautious 30 days and flags it (D53).
- Single message, no conversation history.
- Builder-written eval sets are small and have not had owner review; the answer judge is uncalibrated.
- Free-tier quota and provider overload (503, malformed judge output) limit how often the evals can run.

## 15. Repository layout

```
CLAUDE.md  DECISIONS.md  RESULTS.md  HANDOVER.md  README.md
pyproject.toml  .env.example
docs/        PROJECT_CONTEXT.md  providers.md  observability.md  results.md (generated in Phase 3, not yet present)
data/        manifest.json  processed/ (committed)  raw/ (gitignored)
src/niyam/
  cli.py  config.py
  models/      # interfaces, Gemini adapters, cache, rate limiter, ledger
  corpus/      # download, eCFR parse, build
  rules/       # OPT, STEM OPT and cap-gap rules, business-day calendar
  retrieval/   # Postgres keyword and vector search, fusion, HyDE, rerank
  assistant/   # `niyam ask` pipeline and output checks
  evals/       # retrieval, extraction, answers, pipeline, edge; judge; bootstrap stats
evals/         # eval sets (JSONL), including independent/
results/       # raw output of every measurement
scripts/       # bootstrap
tests/
.githooks/     # pre-commit
```

## 16. Environment variables (names only)
`DECISION_PROVIDER`, `DECISION_BUDGET_USD` (D21), `GEMINI_API_KEY`, `DATABASE_URL`. Further names are in `.env.example`.

## 17. Definition of done
- A deployed or demonstrable assistant that answers in-scope questions with paragraph citations, computed deadlines and stated assumptions, and declines out-of-scope ones.
- Reproducible retrieval comparison and staged evaluations (extraction, answers, pipeline, independent sets) with confidence intervals.
- Judge agreement with the owner's labels reported.
- Monitoring with Langfuse and a CI eval gate.
- README and `docs/results.md` containing only measured numbers that cite `RESULTS.md`, with limitations stated.
- `DECISIONS.md` complete enough for the owner to defend every choice.
