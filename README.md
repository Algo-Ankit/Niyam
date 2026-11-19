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

**Status:** in development. The assistant runs from the command line. Retrieval has been
evaluated. Answer-quality and whole-pipeline evaluations are built but have not been run yet.
There is no web app or public demo yet.

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
  [3] Retrieve provisions: vector search over 8 CFR 214.2(f) (pgvector, k = 5)
        plus the paragraphs the findings cite
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

**Fact extraction** (15 messages): all fields correct on 14 of 15 (R5). One prompt fix later,
all 15 were correct (R6). R6 is optimistic, because the fix was made after reading the R5 miss
on the same set and there is no held-out extraction set yet.

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
| `eval-retrieval OUT [--set FILE] [--hyde]` | Score the retrieval arms |
| `eval-extraction OUT` | Score fact extraction end to end |
| `eval-answers OUT` | Score answers given the gold provisions (judge: Gemma) |
| `eval-pipeline OUT` | Score the whole assistant on in-scope and out-of-scope scenarios |
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
- [x] Retrieval evaluation (keyword, vector, hybrid, HyDE)
- [x] `niyam ask` pipeline with code-checked output
- [ ] Run the answer-quality and whole-pipeline evals and calibrate the judge
- [ ] Web app, Langfuse tracing and online evaluation
- [ ] CI regression gate and a public deployment

## License

MIT. See [LICENSE](LICENSE). The regulation text is a US government work in the public domain.
