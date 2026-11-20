# Deploy runbook (D68)

Recommended pairing: the API on **Render** (free web service, Docker) and the website on
**Cloudflare Pages**. The browser calls the API directly, so CORS must list the site's origin.
The host is the owner's decision (`docs/PROJECT_CONTEXT.md` section 13); nothing is deployed yet.

## Environment variables (names only)

Set these on the host, never in the image. Required ones have no default in `src/niyam/config.py`.

| Name | Required | Notes |
|---|---|---|
| `GEMINI_API_KEY` | yes | Secret. Free-tier key only (D35). |
| `DATABASE_URL` | yes | Secret. Neon connection string (port 5432). |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` | yes | Secrets. |
| `LANGFUSE_HOST` | no | |
| `DECISION_PROVIDER`, `DECISION_BUDGET_USD` | no | Keep the budget at 0 (D21). |
| `CORS_ORIGINS` | yes in production | JSON list, e.g. `["https://<project>.pages.dev"]`. |
| `DEMO_DAILY_CAP`, `ASKS_PER_IP_PER_HOUR` | no | D64 limits. |
| `FORWARDED_ALLOW_IPS` | no | Image default: private ranges and 127.0.0.1 (see below). |
| `STATE_DIR` | no | Image default `/app/.state`; ephemeral on free hosts. |
| `PORT` | no | Image default 8000; Render sets its own. |

## Build and run locally

```bash
docker build -t niyam-api .
docker run --rm -p 8000:8000 --env-file .env niyam-api
curl http://localhost:8000/api/health        # {"status":"ok"}
```

The image runs `uvicorn niyam.api:create_app --factory --host 0.0.0.0 --port $PORT --proxy-headers`
as a non-root user. Only `pyproject.toml`, `uv.lock`, `README.md` and `src/` enter the image.

## Client IP behind the proxy

The per-IP limit (D64) uses the address uvicorn derives from `X-Forwarded-For`. uvicorn trusts
the header only when the TCP peer is in `FORWARDED_ALLOW_IPS`, and then takes the right-most
address that is not itself trusted. Render appends the real client address and does not strip a
client-supplied header, so `FORWARDED_ALLOW_IPS=*` would let a client spoof its IP (uvicorn then
takes the left-most entry). The image therefore trusts only private ranges.

After the first deploy, check it: ask twice from one network and confirm the logs show your
public IP rather than a 10.x address. If all clients appear as one proxy address, narrow
`FORWARDED_ALLOW_IPS` to the peer address the logs show.

## Deploy the API on Render (owner steps)

1. Create a Render account (no card needed for free services) and connect the GitHub repo.
2. New > Web Service > pick the repo; runtime **Docker**; instance type **Free**.
3. Health check path: `/api/health`.
4. Add the environment variables above as secrets.
5. Deploy, then `curl https://<service>.onrender.com/api/health`.

Free-tier behaviour to expect:
- Sleeps after 15 minutes without traffic; the next request waits about a minute.
- No persistent disk: `.state/` (response cache, quota ledger) and the in-memory ask limits
  reset on every restart, including each wake from sleep. Gemini's own free-tier limits still
  stop requests, and no spend is possible while `DECISION_BUDGET_USD` is 0 and the key is free tier.
- 750 free instance hours per month per workspace.

## Deploy the website on Cloudflare Pages (owner steps)

1. Create a Cloudflare account and a Pages project connected to the repo.
2. Root directory `web`, build command `npm run build`, output directory `dist`.
3. Set the API base URL variable that the website defines (D66) to the Render URL.
4. Add the Pages origin to the API's `CORS_ORIGINS` and redeploy the API.

## CI

`.github/workflows/ci.yml` runs ruff, ruff format, mypy and pytest through
`scripts/bootstrap.sh` on every push and pull request. The `web` job is skipped until
`web/package.json` exists, then runs `npm ci`, lint and typecheck when those scripts exist, and
`npm run build`. There is no eval gate yet.
