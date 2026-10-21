# GROW HIKE

A full-stack workspace for Indian and US stock tracking, paper trading, portfolio imports, and explainable experiments. Every order uses **virtual money**. The application never places a broker order.

**Start here:** [Architecture and file guide — README2.md](README2.md) · [Manual tests](docs/MANUAL_TESTS.md) · [Verification record](docs/VALIDATION.md) · [Deployment](docs/DEPLOYMENT.md)

## Run it from a clean checkout

Install Docker Desktop with Docker Compose v2. Open a terminal in the `grow-hike` folder, the one containing `compose.yaml`, and run:

```bash
docker compose up
```

The first run downloads images and packages. Wait for the migration/seed service to finish and for the frontend to print its address. Open **http://localhost:5173**. Click **Explore the seeded demo**, or use:

- Email: `demo@growhike.dev`
- Password: `GrowHike-Demo-2026!`

Demo mode makes no market-provider or LLM requests. Prices and historical charts are clearly labelled synthetic. No API keys are needed. A new personal account starts with **₹10,00,000 of virtual cash**.

Other useful addresses:

| Address | Purpose |
| --- | --- |
| http://localhost:8000/docs | Interactive API documentation |
| http://localhost:8000/openapi.json | Generated OpenAPI contract |
| http://localhost:8000/health | Is the API process alive? |
| http://localhost:8000/ready | Can the API reach its migrated database and Redis? |

To rebuild after code changes:

```bash
docker compose up --build
```

To stop without deleting your data:

```bash
docker compose down
```

The PostgreSQL and Redis volumes keep their data. Do not delete them unless you intend to erase your local portfolios.

## What is implemented

| Area | Included behavior |
| --- | --- |
| Foundation | React + TypeScript + Vite, Tailwind, Recharts, FastAPI, PostgreSQL/pgvector, Redis, Alembic, Docker Compose, CI |
| Authentication | bcrypt, 10-minute JWTs, rotated refresh tokens in httpOnly cookies, CSRF checks, session replay revocation, login limits, Google OAuth with state/nonce/PKCE |
| Market data | One backend service, Yahoo → Alpha Vantage → Twelve Data, currency-aware mappings, shared quotas, cache locks, stale values, provider metrics |
| Paper trading | Append-only ledger, PostgreSQL portfolio row lock, atomic cash checks, idempotent retries, FIFO lots, no shorting or leverage |
| Analytics | Native and INR costs/P&L, execution-time FX, allocations, weekday daily snapshots, INR benchmarks, XIRR, volatility and drawdown |
| Imports — phase 5B | CSV/XLSX column mapping, validation, expiring preview, explicit confirmation, immutable read-only holdings, replay-safe confirmation, encrypted Kite connection |
| Tier 2 | SSE cached prices, watchlists, in-app price alerts, metrics, k6 workload, browser smoke/capture script |
| AI | Headline ingestion, pgvector retrieval, LLM summaries with numbered sources, extractive fallback |
| Forecasts | Optional PyTorch LSTM, 1/3/5-session forecasts, expanding-window evaluation, MAE and directional accuracy against the same naive baseline |
| IPO | Manual GMP scenario calculator; inputs and the arithmetic assumption are visible |
| Presentation | Responsive desktop/mobile layout, dark/light themes, saved theme preference |

**Completion status:** source is provided for the listed features. This is not a claim that all ten phases meet the definition of done. Full Docker/PostgreSQL/browser/provider verification and public deployment could not be executed in the authoring environment. See [the exact validation record](docs/VALIDATION.md).

The supported catalogue has **18 stocks** across NSE, BSE, NASDAQ and NYSE, plus two benchmark indices and USD/INR. This is a curated starting catalogue, not an all-market discovery feed. Extend `backend/app/services/catalog.py` with verified provider symbols, then rerun the seed command.

## Configure optional integrations

Copy the example environment file:

```bash
cp .env.example .env
```

PowerShell equivalent:

```powershell
Copy-Item .env.example .env
```

Edit `.env`, then apply changes:

```bash
docker compose up -d --build
```

| Feature | Settings |
| --- | --- |
| Real market data | `DEMO_MODE=false`; optional `ALPHA_VANTAGE_KEY`, `TWELVE_DATA_KEY` |
| Google sign-in | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`; callback `http://localhost:8000/api/auth/google/callback` |
| Kite holdings | `KITE_API_KEY`, `KITE_API_SECRET`, `ENCRYPTION_KEY`; registered callback `http://localhost:8000/api/broker/kite/callback` |
| LLM summaries and embeddings | `LLM_API_KEY`, compatible `LLM_BASE_URL`, chat model and 1536-dimensional embedding model |
| LSTM training | Build with `INSTALL_ML=true`, then run the training command below |

The seeded shared demo user is disabled when `DEMO_MODE=false`. Create a personal account to use live mode. Use a separate production database; development fixtures are not a real trading history.

Generate an encryption key:

```bash
docker compose exec backend python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Copy the output into `.env` as `ENCRYPTION_KEY`. Keep this key backed up separately from the database. Changing it prevents existing broker tokens from being decrypted; disconnect and reconnect them after a rotation.

Kite's connection is its documented authorization-code/token flow, not a scoped OAuth 2.0 API. This application reads holdings only, but the authorization itself can grant broader broker permissions. The code has no broker order endpoint. Broker sessions usually require reconnection after their next-day expiry.

## Market-data budgets

Checked against official documentation on **20 October 2026**:

| Provider | Published constraint / app behavior |
| --- | --- |
| Alpha Vantage | Free standard allowance: **25 requests/day**. The app enforces 25/day plus a conservative self-imposed 5/minute ceiling. Live US entitlements can require a paid plan. |
| Twelve Data | Basic: **8 credits/minute and 800/day**. The implemented quote/history requests are budgeted individually. Symbol and exchange entitlements still apply. |
| Yahoo Finance | The chart endpoint used here is an unofficial interface; no documented free quota or uptime promise is assumed. App defaults are self-imposed: 30/minute and 2,000/day. |

Sources: [Alpha Vantage support](https://www.alphavantage.co/support/), [Alpha Vantage endpoint documentation](https://www.alphavantage.co/documentation/), [Twelve Data plans](https://twelvedata.com/pricing), [Twelve Data credits](https://support.twelvedata.com/en/articles/5615854-credits), [Yahoo API terms](https://legal.yahoo.com/us/en/yahoo/terms/product-atos/apitnc/index.html).

All users share a Redis cache: quotes **60 seconds**, history **1 hour**, USD/INR **6 hours**. A distributed lock coalesces simultaneous misses. Every actual provider request reserves its minute/day budget atomically before sending. Chart/history/news requests also consume the relevant budget. A fallback with missing credentials or an unsupported symbol is skipped.

A request for an NSE symbol never silently uses the BSE quote for that company. Provider/exchange availability is more important than filling every screen with a number. Upstream failure returns the last known price with `stale=true`; an empty cache returns a controlled 503. Stale prices/FX pause new trades. The UI shows `as_of` and provider information. A successful fetch does not mean the exchange is open or the quote is exchange-real-time.

## Money, execution and FIFO

Send quantities and monetary API inputs as decimal strings, such as `"1.25"`. JSON floating-point amounts are rejected. Python uses Decimal; PostgreSQL uses NUMERIC without a forced monetary scale, so it does not silently round stored money. The frontend uses decimal arithmetic and converts to numbers only for presentation/charts. Dimensionless ML tensors and statistical ratios use floats.

All paper portfolios use **INR cash**. Buying a USD security spends `quantity × USD price × USD/INR`. The execution FX rate is stored permanently. Selling uses today's execution FX and consumes the oldest acquisition lots first. Realized INR P&L includes the FX gain/loss on those shares. Holdings are replayed from the ledger; there is no editable holdings total.

Orders are immediate paper fills at the backend's cached price. There are no commissions, taxes, market-impact fills, dividends, stock-split processing, short positions or margin. Imported average-cost positions do not reconstruct historical FIFO lots and cannot be sold through paper trading.

The automated golden case checks:

1. Buy 10 at 100, buy 10 at 120; at 130: average cost 110, unrealized P&L 400, return 18.18% at display precision.
2. Sell 15 at 130: FIFO realized P&L 350; 5 shares remain at cost 600 and value 650.
3. Remaining unrealized P&L 50; total P&L remains 400.

`test_trading_integration.py` also uses two real PostgreSQL sessions and a synchronization barrier to verify that only one of two competing ₹100 purchases can spend a ₹150 balance. It separately tests simultaneous retries with the same idempotency key. **These PostgreSQL tests are included but were not runnable in the authoring environment.**

## Run the checks

Start the stack first, then run the backend tests and ruff in a disposable `grow_test` database:

```bash
docker compose --profile test run --rm tests
```

The test helper creates only the database named `grow_test`. It does not truncate or delete your application database. Integration rows are unique per test run.

Frontend checks on a machine with Node 22.12 or newer:

```bash
cd frontend
npm install
npm run lint
npm run build
cd ..
```

Direct frontend dependency versions are pinned in `package.json`. A portable npm lock should be generated and committed from the first network-enabled release build. The isolated environment only had Linux-specific cached package metadata, so an incomplete cross-platform lock is deliberately not shipped. Python dependency ranges are bounded in `pyproject.toml`; capture a resolved lock in your release environment as well.

The accounting and risk tests can run even without backend dependencies:

```bash
cd backend
python3 -m unittest discover -s tests -p 'test_accounting.py' -v
python3 -m unittest discover -s tests -p 'test_risk.py' -v
cd ..
```

For real browser checks and screenshot/video capture:

```bash
cd e2e
npm install
npx playwright install --with-deps chromium
npm test
cd ..
```

This script visits the running app, checks the console, retries the same trade, imports a portfolio, exercises the fallback tools, and captures desktop/mobile screenshots under `docs/screenshots/` plus `e2e/artifacts/demo.webm`. It has not been executed in the authoring environment; no screenshots or video are presented as captured evidence here.

## Load test and results

Run the included **k6** workload against your local demo instance:

```bash
mkdir -p load/results
docker compose --profile load run --rm k6
python3 load/summarize.py load/results/summary.json
```

The workload uses 20 concurrent virtual users for 15 seconds and a warmed AAPL quote cache. Thresholds: under 1% failed requests, quote p95 below 500 ms, and over 100 successful quotes. These are targets, not measured claims. `summarize.py` updates the block below using actual k6 output.

<!-- LOAD_RESULTS_START -->
**Not run in the authoring environment.** Docker and k6 were unavailable. No request-rate or latency result is fabricated. Run the commands above to record your machine's results here.
<!-- LOAD_RESULTS_END -->

The CI workflow runs frontend checks, Docker integration tests, browser capture, and k6, then uploads the evidence. The workflow itself has not been executed or claimed green in this handoff.

## Train the experimental LSTM

Set `INSTALL_ML=true` in `.env`, rebuild, then:

```bash
docker compose up -d --build
docker compose exec backend python -m app.services.forecasting AAPL --epochs 25
docker compose exec backend pytest -m ml
```

The first rebuild downloads PyTorch and is substantially larger. In demo mode the training/evaluation data are synthetic and the result is labelled accordingly. Live training needs at least 320 closes; a provider that only returns a compact 100-day series is insufficient.

For each of three chronological origins, the model is reinitialized and its scaler is fitted only on earlier observations. The same 1/3/5-session horizons are evaluated for the LSTM and the constant-price baseline. Results include MAE, directional accuracy, sample counts, training dates, and a visible warning that three origins are only a smoke evaluation. A constant baseline predicts the neutral direction; it is correct directionally only when the actual change is zero. There is no claimed model score until training actually runs.

## Learning path and release status

See [README2.md](README2.md) for the architecture, tables, file responsibilities and a phase-by-phase explanation. [Manual tests](docs/MANUAL_TESTS.md) list expected results. [Deployment](docs/DEPLOYMENT.md) explains Vercel plus Render and the same-origin cookie setup.

The optional CAS PDF parser is not implemented. Public deployment, live credential verification, captured browser media and measured k6 results remain release work. Do not mark a phase complete until its checks pass on your machine or in CI.

Suggested commit message:

```text
feat: build Grow Hike paper trading, portfolio imports and analytics platform
```

## Captured browser media
Project Demo.mp4
https://github.com/Harsh-9110/Grow-hike/blob/main/Project%20Demo.mp4
<!-- BROWSER_MEDIA_START -->
Not captured in the authoring environment. Running the browser smoke script adds actual screenshot links here after a successful run and records a demo video.
<!-- BROWSER_MEDIA_END -->
