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

## R7 2026-11-15 - Retrieval dev split (60 questions), five arms including HyDE
- Value: hit@1 / hit@3 / hit@5 / MRR@10. keyword 0.183 / 0.383 / 0.500 / 0.327; vector
  0.900 / 0.967 / 0.967 / 0.936; hybrid 0.500 / 0.667 / 0.783 / 0.615; hyde 0.817 / 0.917 /
  0.950 / 0.875; vector+hyde 0.867 / 1.000 / 1.000 / 0.925. Paired 95% bootstrap, arm minus
  vector: hyde hit@1 -0.083 [-0.200, +0.033]; vector+hyde hit@1 -0.033 [-0.117, +0.033], hit@5
  +0.033 [0.000, +0.083].
- Produced by: `uv run niyam eval-retrieval results/retrieval-dev-1.json --hyde` at commit
  90af482 (hit@5 interval computed from the raw file with niyam.evals.stats.paired_bootstrap)
- Config: gemini-embedding-2 (768); HyDE passages by gemini-3.5-flash-lite, thinking low,
  embedded as documents; fusion is reciprocal rank (k = 60); 24 candidates per arm; 2,000
  bootstrap resamples, seed 0. Set evals/retrieval-dev.jsonl, builder-written.
- Raw output: results/retrieval-dev-1.json

## R8 2026-11-15 - Retrieval held-out test split (35 questions), confirmation run
- Value: keyword 0.086 / 0.343 / 0.514 / 0.271; vector 0.857 / 0.943 / 0.943 / 0.903 (same as
  R4); hybrid 0.486 / 0.714 / 0.743 / 0.614; hyde 0.771 / 0.914 / 0.971 / 0.852; vector+hyde
  0.800 / 0.971 / 1.000 / 0.888. vector+hyde minus vector: hit@1 -0.057 [-0.171, +0.057],
  hit@5 +0.057 [0.000, +0.143]. Across both splits vector+hyde gained the gold paragraph in the
  top 5 on 4 of 95 questions and lost it on none.
- Produced by: `uv run niyam eval-retrieval results/retrieval-test-1.json --set
  evals/retrieval-test.jsonl --hyde` at commit 90af482
- Config: as R7. Set evals/retrieval-test.jsonl (the R4 questions), builder-written.
- Raw output: results/retrieval-test-1.json

## R9 2026-11-16 - Retrieval dev split (60 questions), vector vs vector + rerank
- Value: hit@1 / hit@3 / hit@5 / MRR@10. vector 0.900 / 0.967 / 0.967 / 0.936; vector+rerank
  0.983 / 1.000 / 1.000 / 0.989. Paired 95% bootstrap, rerank minus vector: hit@1 +0.083
  [+0.000, +0.183], MRR@10 +0.053 [+0.000, +0.112]. Per question at rank 1: 6 fixed, 1 broken,
  1 still wrong (d31). Keyword and hybrid as before (0.183 and 0.500 hit@1).
- Produced by: `uv run niyam eval-retrieval results/retrieval-dev-rerank-1.json --rerank` at
  commit 992eece (fixed/broken counts from the raw rankings)
- Config: gemini-embedding-2 (768); vector top 10 reranked by gemini-decision-1, one yes/no
  question per candidate in one request, ties in vector order (D49); 24 candidates per arm;
  2,000 bootstrap resamples, seed 0. Set evals/retrieval-dev.jsonl, builder-written.
- Raw output: results/retrieval-dev-rerank-1.json

## R10 2026-11-19 - Independent decline and security eval (40 cases)
- Value: passed 0.513 across 40 cases (judge_failed 1: y031). Per-group pass rates:
  category:out_of_scope 0.467 (15 cases, judge_failed 0); category:partly_answerable 0.75 (8 cases,
  judge_failed 0); category:security_guardrails 0.438 (17 cases, judge_failed 1); confidence:high
  0.484 (32 cases, judge_failed 1); confidence:medium 0.625 (8 cases, judge_failed 0); unambiguous
  0.541 (38 cases, judge_failed 1); ambiguous 0.0 (2 cases, judge_failed 0). Overall metrics:
  scope_ok 0.9, deadlines_ok 0.769, counts_ok 0.6, asks_ok 1.0, cites_gold 0.75, no_leak 1.0,
  says_required 0.538, avoids_forbidden 1.0.
- Produced by: `uv run niyam eval-edge results/edge-decline-1.json --set
  evals/independent/decline_and_security.jsonl` at commit 420089f (with uncommitted D62 autocommit
  and progress-logging changes in `src/niyam/cli.py`)
- Config: generator gemini-3.5-flash-lite, decision gemini-decision-1, judge gemma-4-31b-it,
  response cache on; eval set evals/independent/decline_and_security.jsonl (40 cases, 1 run).
- Raw output: results/edge-decline-1.json

## R11 2026-11-19 - Independent H-1B scope and cap-gap eval (70 cases)
- Value: passed 0.493 across 70 cases (judge_failed 1: h070). Per-group pass rates:
  category:cap_exemptions 0.571 (7 cases, judge_failed 0); category:cap_gap 0.0 (9 cases,
  judge_failed 0); category:cos_vs_consular 0.5 (2 cases, judge_failed 0); category:dates 0.692
  (13 cases, judge_failed 0); category:denial_withdrawal 0.6 (5 cases, judge_failed 0);
  category:grace_period 0.2 (5 cases, judge_failed 0); category:messy_input 0.0 (3 cases,
  judge_failed 0); category:out_of_scope 0.714 (8 cases, judge_failed 1); category:portability
  0.25 (4 cases, judge_failed 0); category:registration_selection 0.9 (10 cases, judge_failed 0);
  category:specialty_occupation 0.25 (4 cases, judge_failed 0); confidence:high 0.567 (61 cases,
  judge_failed 1); confidence:medium 0.0 (7 cases, judge_failed 0); confidence:low 0.0 (2 cases,
  judge_failed 0); unambiguous 0.507 (68 cases, judge_failed 1); ambiguous 0.0 (2 cases,
  judge_failed 0). Overall metrics: scope_ok 0.814, deadlines_ok 0.556, counts_ok 0, asks_ok 1.0,
  cites_gold 0.765, no_leak 1.0, says_required 0.551, avoids_forbidden 0.971.
- Produced by: `uv run niyam eval-edge results/edge-h1b-1.json --set
  evals/independent/h1b_cases.jsonl` at commit 8bfb014
- Config: generator gemini-3.5-flash-lite, decision gemini-decision-1, judge gemma-4-31b-it,
  response cache on; eval set evals/independent/h1b_cases.jsonl (70 cases, 1 run).
- Raw output: results/edge-h1b-1.json

## R12 2026-11-21 - Independent edge-cases eval (90 cases)
- Value: passed 0.221 across 90 cases (judge_failed 4: x022, x045, x057, x061). Per-group pass
  rates: category:adversarial 0.444 (9 cases, judge_failed 0); category:cap_gap 0.143 (9 cases,
  judge_failed 2); category:date_boundaries 0.2 (15 cases, judge_failed 0);
  category:messy_language 0.111 (9 cases, judge_failed 0); category:missing_or_contradictory_facts
  0.143 (7 cases, judge_failed 0); category:scope_boundaries 0.0 (11 cases, judge_failed 0);
  category:silent_regulation 0.125 (8 cases, judge_failed 0); category:stem_opt 0.25 (9 cases,
  judge_failed 1); category:unemployment_counting 0.5 (13 cases, judge_failed 1); confidence:high
  0.333 (46 cases, judge_failed 1); confidence:medium 0.091 (35 cases, judge_failed 2);
  confidence:low 0.125 (9 cases, judge_failed 1); unambiguous 0.27 (66 cases, judge_failed 3);
  ambiguous 0.087 (24 cases, judge_failed 1). Overall metrics: scope_ok 0.867, deadlines_ok
  0.571, counts_ok 0.947, asks_ok 1.0, cites_gold 0.851, no_leak 1.0, says_required 0.326,
  avoids_forbidden 0.942.
- Produced by: `uv run niyam eval-edge results/edge-cases-1.json --set
  evals/independent/edge_cases.jsonl` at commit 2640fdb
- Config: generator gemini-3.5-flash-lite, decision gemini-decision-1, judge gemma-4-31b-it,
  response cache on; eval set evals/independent/edge_cases.jsonl (90 cases, 1 run).
- Raw output: results/edge-cases-1.json

## R12 2026-11-20 - Retrieval held-out test split (35 questions), vector vs vector + rerank
- Value: hit@1 / hit@3 / hit@5 / MRR@10. vector 0.886 / 0.943 / 0.943 / 0.917; vector+rerank
  1.000 / 1.000 / 1.000 / 1.000. Paired 95% bootstrap, rerank minus vector: hit@1 +0.114
  [+0.029, +0.229], MRR@10 +0.083 [+0.014, +0.168]. Keyword 0.114 / 0.400 / 0.514 / 0.294;
  hybrid 0.514 / 0.714 / 0.771 / 0.629. Confirms R9 on the held-out split (Phase 2 open item).
  Vector, keyword and hybrid differ slightly from R8 on the same set (vector hit@1 0.857 there);
  the cause was not investigated.
- Produced by: `uv run niyam eval-retrieval results/retrieval-test-rerank-1.json --set
  evals/retrieval-test.jsonl --rerank` at commit 8956547
- Config: as R9 (gemini-embedding-2 768, vector top 10 reranked by gemini-decision-1, 2,000
  bootstrap resamples, seed 0). Set evals/retrieval-test.jsonl, builder-written.
- Raw output: results/retrieval-test-rerank-1.json

## R13 2026-11-21 - Independent edge-case eval (90 cases)
- Value: passed 0.221 across 90 cases (judge_failed 4: x022, x045, x057, x061). Per-group pass
  rates: category:adversarial 0.444 (9 cases, judge_failed 0); category:cap_gap 0.143 (9 cases,
  judge_failed 2); category:date_boundaries 0.2 (15 cases, judge_failed 0);
  category:messy_language 0.111 (9 cases, judge_failed 0);
  category:missing_or_contradictory_facts 0.143 (7 cases, judge_failed 0);
  category:scope_boundaries 0.0 (11 cases, judge_failed 0); category:silent_regulation 0.125
  (8 cases, judge_failed 0); category:stem_opt 0.25 (9 cases, judge_failed 1);
  category:unemployment_counting 0.5 (13 cases, judge_failed 1); confidence:high 0.333 (46 cases,
  judge_failed 1); confidence:medium 0.091 (35 cases, judge_failed 2); confidence:low 0.125
  (9 cases, judge_failed 1); unambiguous 0.27 (66 cases, judge_failed 3); ambiguous 0.087
  (24 cases, judge_failed 1). Overall metrics: scope_ok 0.867, deadlines_ok 0.571, counts_ok
  0.947, asks_ok 1.0, cites_gold 0.851, no_leak 1.0, says_required 0.326, avoids_forbidden 0.942.
- Produced by: `uv run niyam eval-edge results/edge-cases-1.json --set
  evals/independent/edge_cases.jsonl`, started 2026-11-21 13:17 IST with HEAD at c51193a (plus
  the uncommitted D69 changes committed at 13:28). The report's `commit` field says 2640fdb
  because `cli._commit()` reads HEAD when the report is written, 3.5 h later. Between c51193a and
  D73 the only changes to code this eval runs are tracing flush and two deploy settings, so the
  numbers measure the pipeline before D72 (routing) and D73 (timeout).
- Config: generator gemini-3.5-flash-lite, decision gemini-decision-1, judge gemma-4-31b-it,
  response cache on; eval set evals/independent/edge_cases.jsonl (90 cases, 1 run).
- Raw output: results/edge-cases-1.json

## R14 2026-11-21 - Whole-pipeline eval on 40 scenarios
- Value: scope_correct 1.0 (40 of 40); deadlines_agree 1.0; in_scope_shown 0.933 (28 of 30);
  in_scope_cites_gold 0.967 (29 of 30); in_scope_correct 0.9 (27 of 30); in_scope_grounded 0.933
  (28 of 30); unanswerable_abstained 1.0 (4 of 4). Misses: p01 (withheld: word date May 15,
  2026), p29 (withheld: bracketed citation), p20 (shown and grounded, judged incorrect).
- Produced by: `uv run niyam eval-pipeline results/pipeline-1.json` at commit ba8267a
- Config: generator gemini-3.5-flash-lite, thinking level low, decision gemini-decision-1,
  judge gemma-4-31b-it, embedding gemini-embedding-2 (768), retrieval_k 5, response cache on;
  eval set evals/pipeline.jsonl (40 scenarios: 30 in_scope, 4 unanswerable, 6 out_of_scope;
  builder-written, judge uncalibrated).
- Raw output: results/pipeline-1.json
