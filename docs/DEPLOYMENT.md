# Deploy Vercel + Render

No public deployment has been made for this handoff. The following is an executable setup guide after local/CI acceptance. You will need your own Git repository, Vercel project, Render services and integration credentials. Review the resources chosen by the hosting dashboards before creating them.

## 1. Verify locally and in CI

Run the README checks, including real PostgreSQL concurrency tests, ruff, browser console checks and k6. Push the source to your own repository and require the CI jobs to pass. Resolve and commit portable dependency lock files from this network-enabled release environment.

## 2. Provision storage

Create a PostgreSQL database with the `vector` extension available, and a Redis-compatible service reachable by the API and worker. Render documents [supported PostgreSQL extensions](https://render.com/docs/postgresql-extensions). Keep those services private where your hosting setup supports it.

SQLAlchemy expects a URL beginning with `postgresql+psycopg://`, not a legacy `postgres://` prefix. Preserve the database provider's SSL requirements, e.g. `?sslmode=require` when appropriate. Redis TLS URLs use `rediss://`.

Use a new production database. Do not publish a development database containing a shared demo account or synthetic snapshots as real history.

## 3. Deploy API and worker

Use `infra/render.yaml` as the Blueprint path, or manually create:

| Service | Build settings | Start |
| --- | --- | --- |
| API | Repo root Docker context, `backend/Dockerfile.deploy` | `sh /app/start_api.sh` |
| Worker | Same image/settings as API | `python -m app.worker` |

Set the API health check to `/ready`. The API start script runs the migration and catalogue seeder before starting Uvicorn. For the first rollout, start/verify the API before enabling the worker so its tables exist. Use one worker. On later releases, use a controlled migration step before rolling API and worker versions that depend on a changed schema.

Configure the shared environment group:

```dotenv
ENVIRONMENT=production
DEMO_MODE=false
COOKIE_SECURE=true
DATABASE_URL=your actual SQLAlchemy PostgreSQL connection URL
REDIS_URL=your actual Redis URL
JWT_SECRET=your generated random secret
ENCRYPTION_KEY=your generated Fernet key
FRONTEND_URL=https://your actual frontend hostname
BACKEND_URL=https://your actual frontend hostname
```

The example above describes the required values; do not paste the explanatory phrases as environment values. Generate a JWT secret with `python3 -c 'import secrets; print(secrets.token_urlsafe(48))'`. Generate the Fernet key with the README command and keep it separate from the database backup.

**Why BACKEND_URL uses the frontend hostname here:** it means the API's public browser-facing origin. The frontend proxies `/api` to Render. OAuth callbacks must also pass through that frontend origin so the refresh/state cookies belong to the same browser host. Using the Render hostname directly for an OAuth callback would set cookies on the wrong host for this proxy design.

Set provider/Google/Kite/LLM keys only if enabling those features. The Blueprint exposes mandatory settings; add optional integration variables in the hosting dashboard. Never prefix server secrets with `VITE_` or put them in frontend files.

## 4. Configure and deploy Vercel

Once Render gives you the API's actual HTTPS hostname, run from the repository root:

```bash
python3 infra/configure_vercel.py https://YOUR_ACTUAL_API_HOST
```

Replace that argument with the actual API origin, without `/api` at the end. The script writes `frontend/vercel.json` with the correct external proxy and SPA fallback. Commit that generated file.

Create the Vercel project with root directory `frontend`, Vite framework, build command `npm run build`, and output directory `dist`. No market API key belongs in the frontend's environment. Deploy it, then set `FRONTEND_URL` and `BACKEND_URL` on both backend services to this exact HTTPS frontend origin and redeploy them.

See [Vercel rewrite documentation](https://vercel.com/docs/rewrites) and [Render Blueprint reference](https://render.com/docs/blueprint-spec) for hosting syntax. Those pages were consulted on 20 October 2026; dashboard resource offerings can change.

## 5. Register exact callbacks

| Integration | Production callback |
| --- | --- |
| Google web OAuth client | `https://YOUR_FRONTEND_HOST/api/auth/google/callback` |
| Kite app redirect | `https://YOUR_FRONTEND_HOST/api/broker/kite/callback` |

Use the real frontend hostname in those values. The cookie/state paths and callbacks should be tested through Vercel, including refresh and logout. Do not test only by directly opening the Render URL.

Kite's documented session expires the following day around 06:00 IST. Read [Kite login/session documentation](https://kite.trade/docs/connect/v3/user/) and [holdings documentation](https://kite.trade/docs/connect/v3/portfolio/). The app implements holdings reads, not a restricted broker scope or brokerage order placement.

## 6. Verify the deployed behavior

- Create a new personal account and check the initial virtual wallet.
- Inspect Secure/httpOnly cookie flags and test renewal after an access token expires.
- Exercise your providers within actual entitlement limits, including stale-cache failure behavior.
- Confirm the worker heartbeat and a daily observation.
- Check that a stream can remain open without exhausting API database connections.
- Configure trusted proxy IP handling so rate limits use the intended client address.
- Test Google/Kite via the frontend host; verify disconnect and expired-session behavior.
- Run a small load test on the deployment only after confirming the load and data-provider budgets.

A long-lived SSE stream is best-effort through a serverless proxy. Vercel/hosting duration limits can end it; the client reconnects. Validate your specific hosting behavior rather than treating local SSE as proof of indefinite production streaming.

Deployment screenshots/video and a public URL should be added only after these steps actually pass. No URL is fabricated in this project.
