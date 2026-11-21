# Deploy runbook (D68, D69, D70, D71)

Live at **https://niyam-flame.vercel.app**: one Vercel Hobby project with two Services
(D70). `web` (Vite, root `web/`) serves the site; `api` (FastAPI, entrypoint
`src.niyam.asgi:app`) serves `/api/*` on the same origin, so no CORS setup is needed. Every push
to `main` redeploys both. The same API also ships as a container image (below) for any other host.

## Environment variables (names only)

Set these in Vercel (Project > Settings > Environment Variables) or pass them to the container;
never commit them. Required ones have no default in `src/niyam/config.py`.

| Name | Required | Notes |
|---|---|---|
| `GEMINI_API_KEY` | yes | Secret. Free-tier key only (D35). |
| `DATABASE_URL` | yes | Secret. Neon connection string. |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` | yes | Secrets. `LANGFUSE_HOST` if not the default. |
| `STATE_DIR` | Vercel: yes | `/tmp/niyam-state` on Vercel (only `/tmp` is writable). Image default `/app/.state`. |
| `CLIENT_IP_HEADER` | Vercel: yes | `x-real-ip`. Vercel overwrites it with the client IP, so it cannot be spoofed (D69). |
| `ASK_DEADLINE_SECONDS` | no | Default 50; keep below `maxDuration` (60) in `vercel.json` (D71). |
| `DEMO_DAILY_CAP`, `ASKS_PER_IP_PER_HOUR` | no | D64 limits; per instance, so approximate on Vercel. |
| `CORS_ORIGINS` | only cross-origin | JSON list; not needed on Vercel (same origin). |
| `DECISION_PROVIDER`, `DECISION_BUDGET_USD` | no | Keep the budget at 0 (D21). |
| `FORWARDED_ALLOW_IPS`, `PORT` | container only | See "Container" below. |

## Vercel (production)

Set up once: import `Algo-Ankit/Niyam` at vercel.com/new (Application Preset "Services", read
from `vercel.json`), add the variables above, deploy. After that, pushes deploy automatically.

Checks after a deploy:

```bash
curl https://niyam-flame.vercel.app/api/health   # {"status":"ok","corpus_snapshot":"2026-10-15"}
```

Then ask one question on the site, or check Vercel's runtime logs for the `/api/ask` request.

Behaviour to expect:
- Deployment Protection (Vercel Authentication) covers the generated per-deployment URLs; the
  production domain `niyam-flame.vercel.app` is public.
- Each ask runs in one function with `maxDuration` 60 s. Gemini overload (`503`) can make the
  first step take 30 s or more; past `ASK_DEADLINE_SECONDS` the visitor gets the "busy" message
  instead of a cut-off stream (D71).
- The response cache and quota ledger live in `/tmp` and the ask limits in memory, all per
  instance; they reset when instances recycle. Gemini's own free-tier limits remain the hard stop.
- Langfuse traces are flushed after the reply is sent, before the stream closes (D69).

## Container

CI builds the image on every push, starts it with dummy settings, checks `GET /api/health`
(status, snapshot date) and the non-root user, and on `main` publishes it publicly:

```bash
docker pull ghcr.io/algo-ankit/niyam-api:latest
docker run --rm -p 8000:8000 --env-file .env ghcr.io/algo-ankit/niyam-api:latest
curl http://localhost:8000/api/health
```

Tags: `latest` and `sha-<commit>`. The image runs
`uvicorn niyam.api:create_app --factory --host 0.0.0.0 --port $PORT --proxy-headers` as a
non-root user with a `HEALTHCHECK` on `/api/health`. Only `pyproject.toml`, `uv.lock`,
`README.md`, `src/` and `data/manifest.json` enter the image.

Behind a reverse proxy, the per-IP limit uses the address uvicorn derives from `X-Forwarded-For`.
uvicorn trusts that header only from peers in `FORWARDED_ALLOW_IPS` (image default: private
ranges and 127.0.0.1) and takes the right-most untrusted address; `FORWARDED_ALLOW_IPS=*` would
let clients spoof their IP. Alternatively set `CLIENT_IP_HEADER` to a header the proxy overwrites.

## CI & Scheduled Online Eval

- **`.github/workflows/ci.yml`** runs on every push and pull request:
  - `python`: bootstraps `.tools/` + `.venv`, runs `ruff check .`, `ruff format --check .`,
    `mypy`, `pytest`, `niyam eval-gate` (verifying frozen R5–R15 baselines + deterministic
    invariants, D75), and `niyam eval-report --check` (verifying `docs/results.md` is up to date).
  - `web`: `npm ci`, `npm run typecheck`, `npm run build`.
  - `container`: builds the Docker image, checks `GET /api/health` and the non-root user, and on
    `main` publishes `ghcr.io/algo-ankit/niyam-api`.
- **`.github/workflows/online-eval.yml`** runs daily at `03:00 UTC` (or manually via
  `workflow_dispatch`) to execute `niyam online-eval` against Langfuse Cloud traces (D76) and
  upload `online-failures.jsonl` as an artifact when any failures are harvested.
  - Required GitHub Actions secrets (`Settings > Secrets and variables > Actions`):
    `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `GEMINI_API_KEY` (optional `LANGFUSE_HOST`,
    defaults to `https://cloud.langfuse.com`). If any secret is missing, scheduled runs skip
    cleanly (`exit 0`) while manual dispatches fail with a setup message.
