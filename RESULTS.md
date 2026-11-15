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
