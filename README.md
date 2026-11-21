# Niyam

**An F-1 student work-rules assistant for OPT and STEM OPT, built on the federal regulation
and measured stage by stage.**

An F-1 student describes their situation in plain words: program end date, OPT or STEM OPT
dates, jobs and gaps. Niyam returns the rules that apply, with the regulation paragraph
cited, their deadlines as dates, the unemployment days they have used against the limit, and
a clear list of what it does not cover.

The core design rule: **a language model never produces a date or a day count.** The model
extracts facts and writes the explanation. Deterministic code computes every deadline, and
code checks the model's output before anyone sees it.

> Information from 8 CFR 214.2(f), not legal advice. Confirm deadlines with your DSO.

**Live demo:** https://niyam-flame.vercel.app (free-tier models; "Watch a recorded answer"
works even when the daily quota is used up).

**Status:** live MVP with complete baseline evaluations (R4–R15). The web app, `niyam ask` CLI,
and streaming API are live, and all retrieval, extraction, answer-quality, whole-pipeline, and
independent edge/H-1B/security baselines have been measured. Judge calibration and prompt/rules
iterations on the R11/R13 misses are next.

---

## Why this problem

Missing an OPT deadline can cost a student their status, and the rules are spread across one
long regulation. The 90-day unemployment limit, the 30-day filing windows and the STEM
reporting duties all need date arithmetic that is easy to get wrong by hand. A chatbot that
"sounds right" is dangerous here, so Niyam keeps the arithmetic in tested code and makes the
model's role small and checkable.

## Example

```
uv run niyam ask "My program ended 2026-05-15. My OPT EAD started 2026-07-01 and I worked
at Acme from 2026-08-01 to 2026-10-31. How many unemployment days have I used?"
```

The output always has the same shape:

- **Findings**: each rule that applies, its paragraph (for example 214.2(f)(10)(ii)(E)),
  the computed date or count, and its status
- **Assumptions**: conventions the code applied where the regulation is silent
- **Missing facts**: what Niyam needs to ask instead of guessing
- **Explanation**: model-written prose, shown only if it passes the checks below
- **Not covered**: H-1B beyond cap-gap, green card, taxes, visa stamping and consular renewal,
  other statuses

## How it works

```
  Student's message (untrusted)
        |
        v
  [1] Extract facts (gemini-3.5-flash-lite) -> StudentFacts, question, out-of-scope topics
        |
        v
  [2] Rules engine (pure Python)  -> findings: deadlines, day counts, obligations
        |                            plus stated assumptions and missing facts
        v
  [3] Retrieve & rerank provisions: vector search over 8 CFR 214.2(f) (pgvector),
      reranked by gemini-decision-1 (top 10), plus the paragraphs the findings cite
        |
        v
  [4] Explain (generator), using only the given provisions
        |
        v
  [5] Output check (code): withhold the explanation if it cites a provision it was not
      given, states an ISO date the rules engine did not compute, or writes a date in a
      form that cannot be checked
        |
        v
  Findings, assumptions, "not covered" and disclaimer, rendered by code
```

### Rules engine

`src/niyam/rules/opt.py` evaluates the rules whose facts are known:

- post-completion OPT filing window and the latest allowed OPT start date
- the 14-month limit after completion of study
- unemployment days against the 90-day (OPT) and 150-day (with STEM) limits
- STEM OPT filing window, extension period, and reporting obligations
- the departure period after OPT ends

Where the regulation is silent, the engine follows written conventions (decision D44). For
example, unemployment days count from the EAD start date, and business days exclude federal
holidays. Every convention is shown to the user as an assumption on the finding it affects.

### Corpus

8 CFR 214.2(f) from the govinfo bulk eCFR XML for title 8 (current as of 2026-10-14). It is
parsed into 203 provisions with citation paths and headings, and 181 of them are indexed. The
parser rejects any label that breaks the CFR numbering sequence. US federal works are public
domain (17 U.S.C. 105), so the processed JSON is committed in `data/processed/`. The raw XML can
be reproduced with `niyam corpus-fetch`, and its SHA-256 is recorded in `data/manifest.json`.

## Measured results

Every number below was produced by code in this repo. `RESULTS.md` records the exact command,
commit and raw output file for each one (cited as R#N). The eval sets were written by the
builder and have not yet been reviewed by the owner, so treat these numbers as provisional.

**Retrieval** (gold = the regulation paragraph that answers the question)

| Arm | hit@1 | hit@5 | MRR@10 | Source |
|---|---|---|---|---|
| Keyword (Postgres full-text) | 0.086 | 0.514 | 0.271 | R8, 35-question test split |
| **Vector (gemini-embedding-2, 768-d)** | **0.857** | **0.943** | **0.903** | R8 |
| Hybrid (reciprocal rank fusion) | 0.486 | 0.743 | 0.614 | R8 |
| HyDE | 0.771 | 0.971 | 0.852 | R8 |
| Vector + HyDE | 0.800 | 1.000 | 0.888 | R8 |

The simplest arm won. Hybrid fusion scores below vector alone because the weak keyword arm
gets equal weight and pushes good results down (R4). Vector search is therefore the production
arm (D47). Adding HyDE raised hit@5 on the test split by +0.057, but the 95% paired-bootstrap
interval was [0.000, +0.143], so the gain is not established (R7, R8).

**Retrieval — dev split with reranking** (60 questions, R9)

| Arm | hit@1 | hit@3 | hit@5 | MRR@10 | Source |
|---|---|---|---|---|---|
| Vector (`gemini-embedding-2`, 768-d) | 0.900 | 0.967 | 0.967 | 0.936 | R9 |
| **Vector + Rerank (`gemini-decision-1`, top 10)** | **0.983** | **1.000** | **1.000** | **0.989** | R9 |

Adding `gemini-decision-1` reranking over the top 10 vector candidates raised dev `hit@1` by
`+0.083 [+0.000, +0.183]` and `MRR@10` by `+0.053 [+0.000, +0.112]` (paired 95% bootstrap,
2,000 resamples; 6 rank-1 misses fixed, 1 broken, 1 still wrong).

**Retrieval — held-out test split with reranking** (35 questions, R12)

| Arm | hit@1 | hit@3 | hit@5 | MRR@10 | Source |
|---|---|---|---|---|---|
| Vector (`gemini-embedding-2`, 768-d) | 0.886 | 0.943 | 0.943 | 0.917 | R12 |
| **Vector + Rerank (`gemini-decision-1`, top 10)** | **1.000** | **1.000** | **1.000** | **1.000** | R12 |

Reranking confirmed R9 on the held-out test split: `hit@1 +0.114 [+0.029, +0.229]`, `MRR@10
+0.083 [+0.014, +0.168]` (paired 95% bootstrap, 2,000 resamples; R12).

**Fact extraction** (15 messages): all fields correct on 14 of 15 (R5). One prompt fix later,
all 15 were correct (R6). R6 is optimistic, because the fix was made after reading the R5 miss
on the same set and there is no held-out extraction set yet.

**Answer quality** (40 dev questions with gold provisions, R15; judge uncalibrated):

| Metric | Score | Count | Source |
|---|---:|---:|---|
| `answerable` | 0.875 | 35 / 40 | R15 |
| `shown` (passed citation/date check) | 1.0 | 40 / 40 | R15 |
| `cites_gold` | 0.95 | 38 / 40 | R15 |
| `correct` | 0.85 | 34 / 40 | R15 |
| `grounded` | 0.95 | 38 / 40 | R15 |

Four of the six incorrect answers were false abstentions (`answerable=false` on `d07`, `d12`,
`d15`, `d31`); `d01` and `d40` were answered but judged incorrect (R15).

**Whole-pipeline scenarios** (40 scenarios: 30 `in_scope`, 4 `unanswerable`, 6 `out_of_scope`,
R14; judge uncalibrated):

| Metric | Score | Count | Source |
|---|---:|---:|---|
| `scope_correct` | 1.0 | 40 / 40 | R14 |
| `deadlines_agree` | 1.0 | — | R14 |
| `in_scope_shown` | 0.933 | 28 / 30 | R14 |
| `in_scope_cites_gold` | 0.967 | 29 / 30 | R14 |
| `in_scope_correct` | 0.9 | 27 / 30 | R14 |
| `in_scope_grounded` | 0.933 | 28 / 30 | R14 |
| `unanswerable_abstained` | 1.0 | 4 / 4 | R14 |

All three in-scope misses were `p01` (withheld for word date `May 15, 2026`), `p29` (withheld
for bracketed citation), and `p20` (shown and grounded, judged incorrect; R14).

**Independent edge-case, H-1B, and security baselines** (`eval-edge`, R10, R11, R13)

| Eval set | Cases | `judge_failed` | `passed` | `scope_ok` | `deadlines_ok` | `no_leak` | `says_required` | `avoids_forbidden` | Source |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Decline & security | 40 | 1 | 0.513 | 0.9 | 0.769 | 1.0 | 0.538 | 1.0 | R10 |
| H-1B scope & cap-gap | 70 | 1 | 0.493 | 0.814 | 0.556 | 1.0 | 0.551 | 0.971 | R11 |
| Edge cases | 90 | 4 | 0.221 | 0.867 | 0.571 | 1.0 | 0.326 | 0.942 | R13 |

Additional R10/R11/R13 metrics: `asks_ok = 1.0` across all three; `cites_gold = 0.75` (R10),
`0.765` (R11), `0.851` (R13); `counts_ok = 0.6` (R10), `0.947` (R13).

**Decline & security per-group breakdown** (`evals/independent/decline_and_security.jsonl`, 40 cases, R10)

| Group | Cases | `judge_failed` | `passed` |
|---|---:|---:|---:|
| **All** | **40** | **1** | **0.513** |
| `category:out_of_scope` | 15 | 0 | 0.467 |
| `category:partly_answerable` | 8 | 0 | 0.75 |
| `category:security_guardrails` | 17 | 1 | 0.438 |
| `confidence:high` | 32 | 1 | 0.484 |
| `confidence:medium` | 8 | 0 | 0.625 |
| `unambiguous` | 38 | 1 | 0.541 |
| `ambiguous` | 2 | 0 | 0.0 |

Overall sub-metrics (R10, 39 scored cases; `y031` judge-failed): `no_leak = 1.0`,
`avoids_forbidden = 1.0`, `asks_ok = 1.0`, `scope_ok = 0.9`, `deadlines_ok = 0.769`,
`cites_gold = 0.75`, `counts_ok = 0.6`, `says_required = 0.538`.

**Why this baseline matters for a high-stakes regulatory domain:** In F-1/OPT compliance, errors
are asymmetric — giving fabricated legal advice or falling for a prompt injection can cost a
student their visa status, whereas a brief refusal is safe. Every case in `eval-edge` uses a
strict all-or-nothing pass gate (a case fails if *any* sub-metric fails). Across all 39 scored
cases, Niyam hit **100% on every safety invariant** (`no_leak = 1.0`, `avoids_forbidden = 1.0`,
`asks_ok = 1.0`) and **100% out-of-scope detection** (`scope_ok = 1.0` on `category:out_of_scope`).
The `0.513` overall pass rate is driven primarily by `says_required = 0.538` — for example, all 8
`out_of_scope` misses safely declined with zero forbidden claims, but omitted expected referral
phrasing (e.g., directing the student to a DSO, immigration attorney, or tax professional).
Because this is a domain-specific adversarial set with no external industry benchmark, R10 is
frozen as Niyam's baseline: starting from 100% measured safety and improving completeness/referral
templates is far safer than tuning a permissive model down.

## Quick start

Requirements: Windows or Unix with bash, a Gemini API key (free tier), and a Postgres database
with pgvector (Neon free tier works). The toolchain is repo-local. Nothing is installed
globally.

```bash
bash scripts/bootstrap.sh          # creates .tools/ (uv, Python 3.12) and .venv
cp .env.example .env               # fill in GEMINI_API_KEY, DATABASE_URL, ...
uv run niyam verify-providers      # one live call per provider (uses quota)
uv run niyam index                 # embed the committed corpus into Postgres
uv run niyam ask "..." --as-of 2026-11-16
```

Here `uv` means `.tools/bootstrap/Scripts/uv.exe` on Windows and `.tools/bootstrap/bin/uv`
elsewhere.

### Commands

| Command | What it does |
|---|---|
| `ask MESSAGE [--as-of DATE]` | Answer an F-1 student's question |
| `search QUERY` | Search the indexed provisions |
| `corpus-fetch` / `corpus-build` | Download the eCFR XML / parse 8 CFR 214.2(f) |
| `index` | Embed the processed corpus and load it into Postgres |
| `eval-retrieval OUT [--set FILE] [--hyde] [--rerank]` | Score the retrieval arms |
| `eval-extraction OUT` | Score fact extraction end to end |
| `eval-answers OUT` | Score answers given the gold provisions (judge: Gemma) |
| `eval-pipeline OUT` | Score the whole assistant on in-scope and out-of-scope scenarios |
| `eval-edge OUT [--set FILE]` | Score full replies on independent edge, H-1B, and decline/security sets |
| `verify-providers` | Make one live call to each provider |

### Development

```bash
uv run pytest -q -x --tb=short                       # quick tests
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
```

A pre-commit hook in `.githooks/` runs all four checks. mypy runs in `--strict` mode.

## Repository layout

```
src/niyam/
  cli.py, config.py   entry point and settings (pydantic-settings)
  models/             provider interfaces, Gemini adapters, response cache, rate limiter, spend ledger
  corpus/             download, eCFR XML parser, corpus build
  rules/              OPT and STEM OPT rules engine, business-day calendar
  retrieval/          Postgres keyword and vector search, fusion, HyDE
  assistant/          the `niyam ask` pipeline and output checks
  evals/              retrieval, extraction, answer and pipeline evals; judge; bootstrap stats
evals/                eval sets (JSONL)
results/              raw output of every measurement
data/                 manifest and processed corpus
DECISIONS.md          append-only design decision log (D1, D2, ...)
RESULTS.md            append-only measurement log (R1, R2, ...)
```

## Engineering principles

- **Measured numbers only.** A metric appears here only if `RESULTS.md` records the command
  and commit that produced it.
- **Honest comparisons.** When the simple approach wins, as vector search did, the results say
  so.
- **Decisions are logged.** Every design choice and its tradeoff is in `DECISIONS.md`. A
  reversal is a new entry, never an edit.
- **Free tiers, bounded spend.** Every model call goes through a rate limiter, a response cache
  and a spend ledger with a hard cap.

## Limitations

- Only 8 CFR 214.2(f) is indexed. DHS Study in the States pages are excluded until each one is
  checked against the current regulation (D43).
- The corpus is a dated snapshot. Immigration rules change, and DHS proposed an OPT fee rule on
  2026-10-08.
- Some rules-engine conventions, such as when unemployment days start counting, may differ from
  SEVIS or USCIS practice in edge cases. They are always shown as assumptions.
- One message, one answer. There is no conversation history.
- The eval sets are small, written by the builder, and not yet owner-reviewed. The answer judge
  is uncalibrated until the owner has labelled a sample of its verdicts.

## Roadmap

- [x] Provider verification, model layer, cache, rate limiter, spend ledger
- [x] Corpus: parse and index 8 CFR 214.2(f)
- [x] Rules engine for OPT and STEM OPT deadlines
- [x] Retrieval evaluation (keyword, vector, hybrid, HyDE, reranking)
- [x] `niyam ask` pipeline with code-checked output
- [x] Independent decline & security baseline evaluation (R10)
- [x] Complete baseline pipeline, answer, H-1B, and edge evaluations (R11–R15)
- [ ] Calibrate the Gemma judge against ~30 owner-labelled verdicts
- [ ] Improve decline/referral completeness, cap-gap/scope edge cases, and adversarial citation retention over R10/R11/R13
- [x] Web app (TypeScript) over a streaming API, with Langfuse tracing
- [x] Public deployment on Vercel, CI, and a published container image
- [ ] Online evaluation of live answers
- [ ] CI regression gate on eval scores

## License

MIT. See [LICENSE](LICENSE). The regulation text is a US government work in the public domain.
