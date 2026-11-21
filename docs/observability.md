# Observability budget (D67, D76)

Langfuse Hobby allows 50,000 units per month, where units = traces + observations + scores
(Langfuse docs). The target is to stay comfortably under 50,000/month.

## Units per live question (measured structure)

| Item | Count |
|---|---|
| Trace (`answer`) | 1 |
| Observations (root `answer` + 6 stage spans: `extract`, `rules`, `retrieve`, `rerank`, `explain`, `verify`) | 7 |
| Trace scores (`withheld`, `rerank_failed`, `findings`) | 3 |
| **Per live question** | **11** |
| Optional web feedback (`user_feedback` via `POST /api/feedback`) | +1 when submitted |
| Non-question greeting/unrelated reply (D72: root + `extract` + 3 scores) | 6 |

## Asynchronous online evaluation (`niyam online-eval`, D76)

- Runs out-of-band via CLI or daily `.github/workflows/online-eval.yml` (never inline on
  Vercel's 60 s `/api/ask` limit).
- Writes up to **2 scores** per evaluated trace (`online_grounded` when newly judged +
  `failure_type`), bounded by `--max-judge` (default 10/day -> <= 600 units/month).
- Failed or negatively rated traces are upserted into the `niyam-live-failures` Langfuse Dataset
  (dataset items do not consume trace/observation/score units).

## Monthly headroom

- At ~80–100 live questions/day (~2,700/month): `2,700 x 11` = ~29,700 units, plus feedback (~300)
  plus daily `online-eval` (<= 600) = ~30,600 units/month (well below Hobby's 50,000 cap).
- Note: sustained traffic at the full `DEMO_DAILY_CAP=150` every day of a 30-day month
  (`150 x 30 x 11 = 49,500`) leaves only 500 units before hitting 50,000; keep typical demo traffic
  below ~130/day or lower `DEMO_DAILY_CAP` if needed.

## Evaluation runs

Offline evaluation runs (`eval-retrieval`, `eval-extraction`, `eval-answers`, `eval-pipeline`,
`eval-edge`) build `Services` without a tracer (`NO_TRACING`) and never send spans to Langfuse;
raw results are saved under `results/` instead.
