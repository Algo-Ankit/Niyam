# Observability budget

Langfuse Hobby allows 50,000 units per month, where units = traces + observations + scores
(Langfuse docs). The target is to stay under about 35,000. The arithmetic below follows the
trace design in the project context (section 10); it is a plan, not a measurement, and is
re-checked against real usage in Phase 4.

## Units per live question

| Item | Count |
|---|---|
| Trace | 1 |
| Observations: scope guard, keyword retriever, vector retriever, re-rank, evidence guard, generation, verification | 7 |
| Scores: abstained, top re-rank probability, support check, numbers check, user feedback | 5 |
| **Per question** | **13** |
| Online judge on a 10% sample: one generation observation and one faithfulness score, so 2 × 0.1 | 0.2 |
| **Expected per question** | **13.2** |

35,000 / 13.2 ≈ 2,650 live questions per month, or about 88 per day. `DEMO_DAILY_CAP` should be
set at or below that.

## Evaluation runs

Offline evaluation runs are not traced to Langfuse by default: they would cost about
13 units per question per run (a 150-question run is about 2,000 units), and their results are
already saved as predictions in the repo. Tracing a run is opt-in.
