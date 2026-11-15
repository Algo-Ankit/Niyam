# Results (append-only, code-generated numbers only)
Format:
## R#N YYYY-MM-DD - <what was measured>
- Value: ...
- Produced by: <command or script> at commit <hash>
- Config: <model, provider, region, dataset, number of runs>
- Raw output: results/<file>

## R1 2026-11-15 - Generation latency, one RAG-shaped prompt, 4 candidate models
- Value: seconds per call (3 calls each). gemini-3.8-flash 86.55, 62.78, 225.53; gemini-3.7-flash
  128.52, 203.39, 135.55; gemini-3.5-flash 5.72, 6.68, 5.74; gemini-4-hydrogen 8.21, 18.58, 36.4.
  3.7 and 3.8 set abstain=true on question 2 although they cited P2.
- Produced by: `uv run python scripts/bench_generation.py results/gen-bench-candidates.json 3
  gemini-3.8-flash gemini-3.7-flash gemini-3.5-flash gemini-4-hydrogen` at commit a938193
- Config: Gemini API free tier, Interactions API, thinking_level low, 4 passages, 1 run per
  question, no cache
- Raw output: results/gen-bench-candidates.json

## R2 2026-11-15 - Generation latency, second round
- Value: seconds per call (3 calls each). gemini-3.5-flash 4.93, 5.49, 4.2; gemini-3.5-flash-lite
  3.71, 3.36, 3.93; gemini-3.6-flash 5.97, 5.77, 3.7. All nine answers cited and abstained
  correctly.
- Produced by: `uv run python scripts/bench_generation.py results/gen-bench-round2.json 3
  gemini-3.5-flash gemini-3.5-flash-lite gemini-3.6-flash` at commit a938193
- Config: as R1
- Raw output: results/gen-bench-round2.json

## R3 2026-11-15 - Gemma 4 as judge candidate, same RAG-shaped prompt
- Value: seconds per call (3 calls each). gemma-4-31b-it 8.5, 23.21, 17.6; gemma-4-26b-a4b-it
  4.23, 5.27, 5.38. All six answers cited and abstained correctly (31B's abstention answer
  text was empty). An earlier run was cut off by a tool timeout, with calls of 4.8 to 128.5 s,
  so latency is erratic. `verify-providers` judge check: 15.0 s.
- Produced by: `uv run python scripts/bench_generation.py results/gen-bench-gemma.json 3
  gemma-4-31b-it gemma-4-26b-a4b-it` at commit 5cae7ba
- Config: Gemini API free tier, Interactions API, no thinking level, 4 passages, no cache
- Raw output: results/gen-bench-gemma.json

## R4 2026-11-15 - Retrieval on 35 questions, keyword vs vector vs hybrid
- Value: hit@1 / hit@3 / hit@5 / MRR@10. keyword 0.086 / 0.343 / 0.514 / 0.271; vector
  0.857 / 0.943 / 0.943 / 0.903; hybrid (reciprocal rank fusion, k = 60) 0.486 / 0.714 / 0.743 /
  0.614. All five vector misses at rank 1 had the gold paragraph's parent or sibling first.
- Produced by: `uv run niyam eval-retrieval results/retrieval-eval-1.json` at commit d47d234
- Config: gemini-embedding-2, 768 dimensions; 181 indexed provisions of 8 CFR 214.2(f), current
  2026-10-14; keyword arm ORs the query words (plainto_tsquery) ranked by ts_rank_cd; 24
  candidates per arm. Eval set evals/retrieval.jsonl was written by the builder and is not yet
  owner-reviewed.
- Raw output: results/retrieval-eval-1.json

## R5 2026-11-15 - Fact extraction on 15 messages, deadline agreement
- Value: field accuracy 0.992; all fields correct 0.933 (14 of 15); out-of-scope topics
  correct 1.0 (15 of 15); deadlines agree with gold facts 0.909 (10 of 11 messages that have
  deadlines). The miss (e03) added a nameless ongoing "job" from the day after the real job
  ended ("unemployed since"), turning 29 unemployment days into 0.
- Produced by: `uv run niyam eval-extraction results/extraction-eval-2.json` at commit 7f155a6
  (results/extraction-eval-1.json, at 338292b, scored 1.0 on deadlines because that version
  compared only finding dates and status, not day counts; fixed in 7f155a6)
- Config: gemini-3.5-flash-lite, thinking level low, Interactions API, response cache on (the
  second run very likely reused the first run's extractions). Eval set evals/extraction.jsonl was
  written by the builder and is not yet owner-reviewed.
- Raw output: results/extraction-eval-2.json

## R6 2026-11-15 - Fact extraction after the "no invented jobs" prompt rule
- Value: field accuracy 1.0; all fields correct 1.0 (15 of 15); out-of-scope correct 1.0;
  deadlines agree 1.0 (11 of 11). Optimistic: the prompt was changed after reading the R5 miss
  on this same set, and there is no held-out set yet.
- Produced by: `uv run niyam eval-extraction results/extraction-eval-3.json` at commit a5c2d6f
- Config: as R5; the prompt change means no cached responses were reused.
- Raw output: results/extraction-eval-3.json
