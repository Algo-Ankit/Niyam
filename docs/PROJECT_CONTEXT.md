# Niyam: Project Context

Working name: **Niyam** (Hindi for "rule"), package name `niyam`. The owner may rename it.

This file is the single source of truth for what we are building, why, how, and in what order. Read all of it before doing anything. If a later instruction from the owner conflicts with it, the owner wins and you record the change in `DECISIONS.md`.

Date written: 2026-11-14.

---

## 1. What we are building

**One line:** a question-answering assistant over the Reserve Bank of India's payment regulations that answers only from the official text, cites the exact clause, and says "not covered" when the documents do not support an answer.

**Who it is for.** Product managers, founders, and compliance or operations staff at fintech companies who need a fast first answer to "what do the rules say about X?" with a clause they can verify.

**Example questions it should answer**
- What is the maximum balance allowed in a full-KYC prepaid instrument?
- Is cash withdrawal permitted from a small PPI?
- What due diligence must a payment aggregator do before onboarding a merchant?
- How long can a small PPI with cash loading be held before conversion to full KYC?

**Example questions it must decline**
- Anything outside the indexed documents (income tax, SEBI rules, company-specific advice, "should we do X").

**Why this case.** Real public documents, an official set of question-and-answer pairs to test against (RBI's own FAQs), and a domain where a confident wrong answer is worse than no answer, which makes evaluation and guardrails meaningful.

### Non-goals (v1)
- Not legal advice, and it must say so on every answer.
- No chat history or multi-turn conversation. One question, one answer.
- No user accounts, billing, or uploads.
- No automatic re-crawling. The corpus is a dated snapshot.
- No agent loops or tool use beyond retrieval.

**Scope discipline.** This project was chosen because it is small. Do not add features, services, or phases that are not in this file. If you think something is missing, raise it in a briefing; do not build it.

---

## 2. Why this project exists (optimise for this)

The owner is an AI engineer adding a RAG project to a resume and will publish the results. It must show, with real evidence:

1. A retrieval pipeline with measured comparisons between approaches.
2. Use of a decision model (Jev) for re-ranking and answer verification.
3. Guardrails: abstain when evidence is missing; verify every answer against its sources.
4. Offline evaluation of retrieval and of answers, with a CI regression gate.
5. Online evaluation and monitoring with Langfuse.
6. A deployed, working demo.

Consequences:

- **Measured numbers only.** Never write a metric into the README, docs, or commit messages that was not produced by code in this repo.
- **Honest results.** If the simple approach beats the fancy one, report that.
- **Simple and legible beats clever.** The owner must be able to explain every part in an interview.

---

## 3. Roles and working agreement

**Owner (human): architect and decision maker.** Sets goals, approves plans, makes tradeoff decisions, reads results, and does three hands-on tasks: picks the topic scope, checks a sample of the test set, and hand-grades a sample of answers.

**You (Claude Code): builder.** You collect documents, write code and tests, run evaluations, deploy, and brief the owner.

### Process for every phase
1. **Plan:** a short plan (what, which files, how verified, open questions). Wait for approval.
2. **Build** in small commits, one logical change each.
3. **Verify:** run tests and the phase's acceptance checks; show real output.
4. **Brief:** at most one page: what was built, what was found, numbers and how they were computed, problems, decisions needed.
5. **Stop at the gate** until the owner approves.

### Standing rules
- **Decisions log:** every non-trivial choice goes in `DECISIONS.md` in the same commit (date, decision, why, tradeoff). Seed it from section 12.
- **Money:** nothing paid beyond the Jev cap in section 4 without approval. Report spend in every briefing.
- **Isolated environment, no global changes.** All Python work happens inside a project-local virtual environment (`.venv` in the repo root, created and managed by `uv`). Never run `pip install` or `uv pip install` against the system or user Python, never use `sudo`, never install global packages or tools, and never edit shell profiles, global git config, or anything outside the repo directory. Run everything through `uv run` or the activated `.venv`. If a system-level tool is genuinely required, stop and ask first. `.venv` is gitignored.
- **Secrets:** only in `.env` (gitignored) and GitHub Actions secrets. Never print or commit them. Provide `.env.example`.
- **Verify provider APIs before coding against them** (section 5). Read current official docs and confirm with one real call. Do not code from memory for Jev, Gemini 4, the Gemini embedding model, or Langfuse.
- **Teach:** in each briefing, explain new concepts in two or three plain sentences and say what the owner should be able to explain back.
- If something behaves differently from this file, stop and report. Do not work around it silently.

---

## 4. Hard constraints

| Constraint | Detail |
|---|---|
| Budget | Free tiers everywhere. Only paid item is Jev: **hard cap 5 USD total**, enforced in code by a spend ledger. |
| Decision model | Jev (TypeSafe AI): relevance grading, scope check, answer-support check. |
| Generative model | `gemini-4-hydrogen` on the Gemini API free tier: writes answers, acts as a sampled judge. |
| Embeddings | A Gemini embedding model on the free tier, if available. If not, the system must still work on keyword search plus Jev re-ranking. |
| No local model inference | No local LLMs or GPU. scikit-learn/numpy on CPU is fine. |
| Data | Official RBI documents only. Free-tier Gemini traffic may be used by Google to improve products; that is acceptable because documents are public and user questions carry a notice. |
| Observability | Langfuse Cloud Hobby (free): 50,000 units per month (traces + observations + scores), 30-day retention. |
| Hosting | Free tiers only. One service. |
| Stack | Python 3.12, FastAPI, Postgres (Neon free) with pgvector and full-text search, `uv`, ruff, pytest. |

---

## 5. Providers: what is known and what to verify

All of this is reported from public sources as of 2026-11-14. **Unverified until you confirm against current docs and one real call.** Write findings to `docs/providers.md`.

**Jev (TypeSafe AI)**
- Discriminative "System One" model released 2026-09-15; reported version `jev-1.13.0`. It does not generate text. Input: a state (text or JSON) plus typed questions (yes/no, choice, scale). Output: typed answers with probabilities.
- Price 0.042 USD per million input tokens, output free. Reported latency 70 to 500 ms. Reported context about 32k tokens.
- Vendor-acknowledged weaknesses: counting and date comparison. **All numeric and date checks are done in code.**
- Access, in order of preference: (1) Vercel AI Gateway on the free monthly credit, reported id `typesafe-ai/jev`; do not purchase credits there, a purchase ends the free credit. (2) OpenRouter, reported id `typesafe/jev-1.13`, minimum purchase 5 USD plus fee, only if route 1 fails and the owner approves. (3) Direct API, waitlisted.
- **It is not a chat-completions model.** Do not wrap it as one. The request is a state plus typed questions; the response is typed answers with probabilities.
- **Batching:** when several questions apply to the same state (for example several checks on one answer), send them in one request if the API allows. Re-ranking is the opposite shape (one question, many passages); check whether multiple passages can be graded in one request, and if not, run the calls concurrently within rate limits.
- **Sources disagree on details.** Different write-ups report different model ids (for example 1.13 and 1.14) and different gateway endpoint paths. Treat every id and path as unknown until confirmed from the provider's own current documentation and one live call.
- Must verify: request/response shape; exact model id and endpoint on the chosen route; whether probabilities come through the gateway; **billing semantics** (state billed once per call or once per question); whether many passages can be graded in one call; rate limits.
- **Jev is optional. No-Jev mode:** if no free route works in Phase 0, do not purchase credits. Stop, report, and with the owner's approval run without Jev: `gemini-4-hydrogen` performs the scope check and the support check (as one structured call each), re-ranking is skipped, and the retrieval comparison covers arms A to C only. The `DecisionModel` interface must make this a config change. Record the outcome in `DECISIONS.md`.

**Gemini 4 Hydrogen**
- Model id `gemini-4-hydrogen`, released 2026-11-12, free tier with rate limits that are shown only in Google AI Studio. Read and record them.
- Reported thinking levels low to xhigh, default high. Use the lowest that gives good answers.
- Rate limiter with backoff on 429 is required. Cache every generation.

**Gemini embeddings**
- Verify the current embedding model name, dimension, and free-tier limits. Batch requests. Cache vectors by content hash.

**Langfuse**
- Check the current Python SDK and API. Budget units: estimate units per question and keep monthly use under about 35k. Put the arithmetic in `docs/observability.md`.

**Design requirement:** every model sits behind an internal interface (`DecisionModel`, `GenerativeModel`, `Embedder`) with provider adapters, a response cache keyed by (provider, model version, prompt/question version, input hash), and a cost ledger. Switching provider is a config change.

---

## 6. The knowledge base

**Source:** the official RBI website (rbi.org.in). Only official regulatory text is indexed.

**Initial scope (owner confirms in Phase 1):**
- Master Direction on Regulation of Payment Aggregators (dated 2025-09-15, later updated).
- Master Directions on Prepaid Payment Instruments (dated 2021-08-27, as amended).
- The current KYC Master Direction (a 2025 direction replaced the 2016 one; confirm which is in force).
- A small number of related directions or circulars (digital lending, card-on-file tokenisation) if they are needed to answer the test questions.

Target size: 10 to 20 documents. Prefer the HTML version of each document over the PDF where both exist.

**Rules for the corpus**
- Download each document once, politely (pauses between requests, a clear user agent). Save raw files under `data/raw/` (gitignored).
- Write `data/manifest.json`: title, URL, RBI reference number, document date, "updated as on" date, download date, content hash.
- Index only versions currently in force. If a document says it supersedes another, do not index the superseded one. Record the check.
- **Check RBI's website terms and copyright notice** before deciding whether the processed text can be committed or published. If unclear, commit only the downloader and manifest, not the text. Report what you find.
- The snapshot date is shown on every answer in the UI.

**Not indexed:** RBI FAQ pages (they are the test set), news, law-firm commentary, anything unofficial.

### Chunking
- Structure-aware: one chunk per clause or sub-clause, never splitting mid-clause when avoidable. Keep tables intact.
- Each chunk stores: document id, hierarchy path (document > chapter > clause > sub-clause), clause label as printed, text, source URL, token count.
- Prepend the hierarchy path to the chunk text used for search, so a clause is findable by its chapter context.
- Stable chunk ids, so evaluation labels survive re-indexing.
- One experiment only: structure-aware chunks versus fixed-size chunks with overlap, compared on retrieval metrics.

---

## 7. The test set

**Primary source:** RBI's official FAQ pages for the topics in scope (for example the Prepaid Payment Instruments FAQ, which has numbered questions each with an official answer). These are never indexed.

**Each test item has:** id, question, reference answer, source FAQ URL, type (numeric, yes/no, definition, procedural, multi-document), gold supporting chunk ids in the corpus, a validity flag, and notes.

**Building it**
1. Parse the FAQ pages into question/answer pairs.
2. For each pair, propose the supporting clause(s) in the corpus. The owner reviews a sample of at least 30 mappings.
3. **Staleness check:** FAQs can lag behind amended directions. For each item, check the reference answer against the current clause. If they disagree, mark the item stale and either correct the reference from the current text (noting it) or drop it. Count and report these.
4. Add an **unanswerable set** of about 30 questions the corpus cannot answer: clearly out of scope (tax, securities) and near-miss questions that sound in scope but are not covered. Expected behaviour: abstain.
5. If the usable total is under about 120, the owner writes more questions by hand with their supporting clause.

**Splits:** a dev set for tuning and a test set that is run only for final results. Fix the split once and save the ids. Never tune on test.

---

## 8. Architecture

```
  User question
        |
        v
  [1] Scope guard (Jev)  ---- out of scope ----> polite decline
        |
        v
  [2] Retrieve candidates
        - keyword search (Postgres full-text)
        - vector search (pgvector)
        - merge with reciprocal rank fusion  -> top 20
        |
        v
  [3] Re-rank (Jev): "Does this passage help answer the question?"
        probability used as score            -> top 5
        |
        v
  [4] Evidence guard: if no passage clears the threshold -> abstain
        |
        v
  [5] Generate (gemini-4-hydrogen): answer only from the 5 passages,
        cite clause labels, structured output
        |
        v
  [6] Verification guard
        - numbers check (code): every amount, limit, date, and percentage
          in the answer must appear in a cited passage
        - support check (Jev): is each claim supported by its cited passage?
        - fail -> one retry, then abstain
        |
        v
  Answer + citations + "not legal advice" + snapshot date
        |
        +--> Postgres (question log, feedback)   +--> Langfuse (trace, scores)
```

**One service.** FastAPI serves the API and a small server-rendered page. Postgres holds chunks, vectors, the keyword index, question logs, and feedback. No queue, no worker, no second deployment.

**Public demo protection.** Per-IP rate limit, a global daily cap sized to the free quotas, and an answer cache for repeated questions. When the cap is hit, show a clear message.

### Guard details
- **Scope guard:** Jev yes/no on "Is this a question about RBI regulation of payments, prepaid instruments, payment aggregators, or related KYC?" Low-confidence cases pass through to retrieval; the evidence guard catches them.
- **Evidence guard:** threshold on the top re-rank probability, chosen on the dev set to balance false abstentions against wrong answers. The owner picks the operating point.
- **Verification guard:** numbers are checked by code because the decision model is weak at them. The Jev support check runs per claim against the cited passage only.
- **Untrusted input:** the user's question is untrusted. Keep it in a delimited field, never let it alter instructions, cap its length. The documents are trusted.
- **Always shown:** "This is not legal advice. Verify against the cited clause." and the corpus snapshot date.

### Abstention wording
Neutral and useful: say the indexed documents do not cover the question, and list which documents are indexed.

---

## 9. Evaluation

### 9.1 Retrieval (needs no generative model, so it is fast and free)
Arms:
- A: keyword only
- B: vectors only
- C: hybrid (A + B fused)
- D: hybrid + Jev re-rank
- Plus the chunking comparison on the best arm.

Metrics: recall@5, recall@10, MRR against gold chunks, by question type. Latency and cost per query.

### 9.2 Answers
- **Correctness** against the reference answer: exact numeric match by code for numeric questions; a `gemini-4-hydrogen` judge for the rest.
- **Faithfulness:** share of answers where every claim is supported by cited passages.
- **Citation precision:** share of cited chunks that actually support the claim.
- **Abstention:** on the unanswerable set, how often it correctly declines; on answerable questions, how often it wrongly declines.
- Latency p50/p95 and cost per question.
- With and without each guard, to show what each one buys.

### 9.3 Validating the judge
The owner hand-grades about 40 answers (correct / partly / wrong, plus supported or not). Report agreement between the automatic judge and the owner. Automatic scores are only trusted to the extent this agreement supports.

### 9.4 Reporting
- Every number with a bootstrap confidence interval and the command that produced it.
- `docs/results.md` is generated by code from saved predictions.
- An error analysis section: group failures into causes (retrieval miss, wrong chunk ranked first, cross-document question, stale source, generation error, over-abstention) with counts and examples.

### 9.5 CI gate
GitHub Actions on every push and PR: ruff, unit tests, then retrieval metrics on the dev set and answer metrics on a fixed 50-question subset using the response cache. Fails if metrics fall below thresholds in `evals/gate.yml`. Fork PRs run without secrets, cache only.

### 9.6 Quota awareness
Generation is rate-limited on the free tier. Cache all generations and judge calls. Run full answer evaluations in batches if needed and say how long a full run takes.

---

## 10. Observability

- **Langfuse:** one trace per question with spans for scope guard, each retriever, re-rank, evidence guard, generation, verification. Scores on each trace: abstained, top re-rank probability, support-check result, numbers-check result, user feedback (thumbs).
- **Online evaluation:** the Jev support check runs on every live answer (cheap). A `gemini-4-hydrogen` judge reviews a sample (about 10%) for faithfulness.
- **Structured logs:** JSON, one correlation id per request, no secrets.
- **Question log table:** question, retrieved chunk ids, scores, answer, citations, guard outcomes, latency, cost, versions.
- **Cost ledger:** tokens and USD per provider per day; hard stop at the Jev cap.
- **Feedback loop:** a script exports thumbs-down and guard-failed questions into a review file; reviewed items can be added to the dev set.
- `/healthz` and a small JSON status endpoint (daily volume, abstention rate, guard failure rate, quota remaining).

---

## 11. Phases

Five phases. Each has a deliverable, acceptance checks, and an owner gate.

### Phase 0: Setup and provider verification
- Repo scaffold (`uv`, ruff, pytest, pre-commit, `.env.example`, MIT license, `CLAUDE.md` pointing to this file, `DECISIONS.md` seeded from section 12).
- One verified real call each to Jev, `gemini-4-hydrogen`, the embedding model, Langfuse. Findings in `docs/providers.md`, including the Jev billing test and all rate limits.
- Model interfaces, adapters, response cache, cost ledger with hard cap.
- **Accept:** `make verify-providers` passes; every "must verify" item in section 5 answered; budget recalculated from real billing.
- **Gate:** owner confirms the Jev route and the embedding choice.

### Phase 1: Corpus and test set
- Document list confirmed with the owner; downloader; manifest; in-force check; terms/copyright check.
- Parser and structure-aware chunker; chunks loaded into Postgres.
- FAQ parser; gold-chunk mapping; staleness check; unanswerable set; splits.
- `docs/dataset.md`: counts, exclusions, stale items, known limitations.
- **Accept:** 20 random chunks checked by hand against the source; test set has the target size; owner has reviewed at least 30 mappings.
- **Gate:** owner approves the corpus and test set.

### Phase 2: Retrieval
- Keyword search, vector search, fusion, Jev re-rank.
- Retrieval evaluation for arms A to D and the chunking comparison.
- **Accept:** reproducible with one command; results with confidence intervals; a short error analysis of retrieval misses.
- **Gate:** owner chooses the production retrieval arm.

### Phase 3: Answering and guards
- Generation with citations; scope, evidence, and verification guards; abstention.
- Answer evaluation (section 9.2), judge validation with the owner's hand grades, guard ablations, threshold selection.
- `docs/results.md` generated.
- **Accept:** test set run once; results include abstention behaviour and error analysis.
- **Gate:** owner picks the evidence threshold and reviews failures.

### Phase 4: App, monitoring, CI, deploy
- FastAPI endpoint and page (question box, answer, citations with links to the source clause, disclaimer, snapshot date, thumbs).
- Rate limiting, daily cap, answer cache.
- Langfuse tracing and scores, online evaluation, status endpoint, feedback export.
- CI with the eval gate; Docker; deploy to a free host; migrations on deploy.
- README: problem, architecture diagram, measured results, limitations, live link.
- **Accept:** public URL works; a question produces a trace with all spans and scores; the CI gate fails when a deliberate regression is introduced.
- **Gate:** owner reviews the live demo and README before it is shared.

---

## 12. Decisions already made (seed `DECISIONS.md`)

1. **Use case:** RBI payment regulations Q&A. Real public documents, an official FAQ test set, and a domain where wrong answers matter.
2. **Official text only** in the knowledge base, so every answer traces to the regulator.
3. **FAQs are the test set and are never indexed,** to keep the evaluation honest.
4. **Abstain over guess.** A wrong compliance answer is worse than no answer.
5. **Jev for relevance, scope, and support checks; Gemini 4 Hydrogen for writing answers.**
6. **Numbers and dates are verified by code,** because the decision model is weak at them.
7. **Postgres for everything** (chunks, vectors, keyword index, logs). One database, one service.
8. **Dated snapshot, no live crawling,** so answers are reproducible and testable.
9. **The automatic judge is validated against the owner's hand grades** before its scores are reported.
10. **Jev budget cap 5 USD,** enforced in code.

## 13. Open decisions for the owner
- Final name.
- Exact document list and whether digital lending and tokenisation are in scope.
- Evidence threshold (how cautious the assistant is).
- Whether processed document text is committed, depending on RBI's terms.
- Free host.

## 14. Known limitations to state openly
- Cross-references between documents (for example payment aggregator rules pointing to KYC rules) are not followed automatically in v1. Measure how many test questions need more than one document and report performance on them separately.
- The corpus is a snapshot; regulations change.
- FAQ answers can be outdated; stale items are corrected or removed and counted.
- Single-turn only.

## 15. Repository layout (target)

```
niyam/
  CLAUDE.md  DECISIONS.md  README.md
  pyproject.toml  Makefile  Dockerfile  .env.example
  docs/        PROJECT_CONTEXT.md  providers.md  dataset.md  results.md  observability.md
  data/        manifest.json   (raw/ and processed/ gitignored unless terms allow)
  src/niyam/
    config.py
    corpus/      # download, parse, chunk, load
    models/      # interfaces, adapters, cache, ledger
    retrieval/   # keyword, vector, fusion, rerank
    guards/      # scope, evidence, numbers check, support check
    answer/      # generation, citations, abstention
    service/     # FastAPI app, page, rate limiting
    observability/
  evals/         # testset/, run_retrieval.py, run_answers.py, judge.py, gate.yml
  tests/
  .github/workflows/ci.yml
```

## 16. Environment variables (names only)
`JEV_PROVIDER`, `JEV_API_KEY`, `JEV_BUDGET_USD`, `GEMINI_API_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`, `DATABASE_URL`, `DEMO_DAILY_CAP`.

## 17. Definition of done
- Live demo that answers in-scope questions with clause citations and declines out-of-scope ones.
- Reproducible retrieval comparison (arms A to D) and answer evaluation with guard ablations.
- Judge agreement with human grades reported.
- CI with an eval gate.
- Langfuse traces with online scores from real usage.
- README and results containing only measured numbers, with limitations stated.
- `DECISIONS.md` complete enough for the owner to defend every choice.
