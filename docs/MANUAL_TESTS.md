# Manual acceptance checklist

Run against a fresh local demo database. If you have already traded, your totals will differ. Keep the browser's Developer Tools Console open and watch `docker compose logs -f backend worker` in a second terminal. Normal use should produce no browser errors or unhandled backend tracebacks. That condition has not been verified in this handoff environment.

## Start and authenticate

- [ ] Run `docker compose up`. Expected: PostgreSQL and Redis become healthy; migration exits with code 0; API readiness succeeds; frontend starts on port 5173.
- [ ] Open `/health` and `/ready` on port 8000. Expected: HTTP 200, `ok` and `ready` respectively.
- [ ] Click **Explore the seeded demo**. Expected: overview with a synthetic-data banner and four holdings.
- [ ] On a fresh seed, verify virtual cash **₹7,88,840.00**, holdings value **₹2,34,820.00**, total value **₹10,23,660.00**, total/unrealized P&L **₹23,660.00**, realized P&L **₹0.00**.
- [ ] Switch to light mode and reload. Expected: light mode stays selected; the session renews without entering the password again.
- [ ] Inspect Application → Cookies. Expected: `gh_refresh` is httpOnly; `gh_csrf` is readable; no token is in localStorage/sessionStorage. Only the theme preference is stored locally.
- [ ] Sign out, register a different valid email and a 12-character-or-longer password. Expected: new personal portfolio with ₹10,00,000 virtual cash and no holdings. No email is sent.
- [ ] Sign out and enter a wrong password. Expected: generic error without revealing whether an account exists.
- [ ] Attempt repeated invalid logins. Expected: 429 after the account/IP budget is exhausted; retry is allowed after the five-minute window. Do this last so it does not block earlier checks.
- [ ] With a personal account, open two tabs and allow token renewal. Expected in browsers supporting Web Locks: refresh calls serialize. Signing out invalidates that session's access token.

## Markets and trading

- [ ] Open Markets; search for `AAPL`, `TCS`, `NYSE`, and a nonsense string. Expected: supported catalogue matches; nonsense has a clear empty state.
- [ ] Select Indian and US stocks. Expected: native INR/USD formatting, source/as-of information, and a price chart. Demo charts are synthetic and labelled.
- [ ] Open the same stock repeatedly, then Metrics. Expected: cache hits and API-calls-saved counters increase. Demo mode never produces external provider calls.
- [ ] In Paper trading, buy one RELIANCE.NS share. Expected: one new BUY ledger entry; cash decreases by ₹1,460; quantity increases by one.
- [ ] Press the same buy button again without changing the order. Expected: “already recorded” message; ledger count and cash do not change.
- [ ] Change quantity, then buy again. Expected: a new order/key is created.
- [ ] Try spending more than your cash, or selling more than you own. Expected: 409 with a useful message; no additional ledger entry.
- [ ] Sell held shares. Expected: cash increases; realized P&L uses FIFO acquisition costs. Remaining holdings retain the remaining lot costs.
- [ ] Run the automated golden and PostgreSQL concurrency tests. Expected: exact golden numbers and only one competing spend. Manual clicking is not evidence of concurrency safety.
- [ ] Enable Live cached updates. Expected: initial SSE quote followed by shared-cache updates roughly once a minute. Navigate away: the stream is aborted.

## Analytics and scheduled jobs

- [ ] Change allocation between stock, sector, market and currency. Expected: each allocation totals approximately 100% after display rounding; cash is excluded.
- [ ] Switch the performance chart to benchmarks. Expected: all series start at 100 at the first observation; S&P 500 includes recorded USD/INR conversion.
- [ ] Check risk statistics. Expected: same-day new accounts show unavailable XIRR; insufficient histories show unavailable risk metrics rather than invented zeros.
- [ ] Run `docker compose exec worker python -c 'from app.services.jobs import snapshot_job; snapshot_job()'` on a weekday. Expected: one daily observation; repeating updates the same date without a duplicate row. Weekend runs do not create an observation.
- [ ] Understand the observation time: 23:45 IST is not the close of every exchange. The chart is a daily observation series.

## Watchlist and alerts

- [ ] Watch a stock from Markets. Expected: it appears once in Watchlist, including when Watch is clicked twice.
- [ ] Create an alert below a stock's current demo price with direction “at or above.” Expected: after the worker's next minute check, it is marked triggered.
- [ ] Refresh the watchlist and delete an alert. Expected: current state appears; removed items stay removed.

## Portfolio imports — phase 5B

- [ ] Download the sample CSV, upload it, and click Validate & preview. Expected: four validated rows; no portfolio exists yet.
- [ ] Confirm. Expected: a separate read-only imported portfolio appears. Paper cash/history are unchanged.
- [ ] Try to trade that imported portfolio. Expected: UI explains it is read-only; the server also rejects orders.
- [ ] Compare imported valuation and allocation with the same stocks' quotes. Expected: same cached market service and exact decimal calculations; native average costs are preserved.
- [ ] Reconfirm the same preview ID through the API. Expected: the same portfolio ID, with no duplicate imported lots.
- [ ] Rename CSV headers and fill in the three mapping fields. Expected: preview uses your mapped columns.
- [ ] Try an XLSX with equivalent values. Expected: equivalent validated rows. Formula cells without cached values are rejected; formulas are not evaluated.
- [ ] Try zero/negative/non-numeric quantity, duplicate symbols, unknown symbols, a file over 2 MB, and unsupported `.xls`/PDF. Expected: clear validation error and no saved holdings.
- [ ] Leave a preview for over 30 minutes, then confirm. Expected: 410; upload again.
- [ ] As a second account, try the first account's portfolio or preview ID. Expected: 404.

## Optional live/integration checks

Use personal accounts and configured credentials. These checks require internet access and have not been executed in this handoff.

- [ ] Set `DEMO_MODE=false`, rebuild and create/sign into a personal account. Expected: seeded demo credentials are disabled; quotes identify a provider and real as-of timestamps.
- [ ] Configure fallback provider keys and verify a symbol covered by your plan. Expected: fallback retains its exchange/currency identity. Entitlement failures are not treated as real quotes.
- [ ] Warm a live quote, then temporarily block its upstream providers in a controlled test environment. After its 60-second cache expiry, expected: last known value with `stale=true`, while trading returns 409. First-ever symbols with no cached data return 503.
- [ ] Stop Redis briefly. Expected: `/ready` becomes 503; authentication fails closed; previously stored market data may be served stale. Restart Redis before continuing.
- [ ] Configure Google credentials and exact callback URI. Expected: Google sign-in creates a paper portfolio; invalid/reused state fails; an existing password email is not silently linked.
- [ ] Configure Kite and encryption key. Expected: connect → holdings preview → explicit confirmation. Expired tokens require reconnecting. A database inspection sees encrypted token text, never a raw token.
- [ ] Disconnect Kite. Expected: local broker token is removed; the earlier imported snapshot remains. Disconnect does not promise revocation of all permissions at the broker.

## AI and IPO

- [ ] Open AI lab in demo mode. Expected: no invented news; an explicit headline fallback and untrained-model state beside the naive baseline.
- [ ] In live mode, fetch actual news without an LLM key. Expected: source headlines and clickable source URLs.
- [ ] Configure a valid LLM/embedding key. Expected: numbered citations match the provided source list. No extra unverified URLs appear.
- [ ] Simulate an LLM outage. Expected: source headlines remain usable; no broken page.
- [ ] Build with PyTorch and train AAPL. Expected: 1/3/5-session model and baseline forecasts, three chronological origins, MAE and directional accuracy, timestamps and an experimental label. Demo results remain labelled synthetic.
- [ ] IPO defaults: issue price 100, GMP 15, subscription 3. Expected: listing scenario ₹115.00 and 15% implied premium; changing subscription alone does not change the arithmetic estimate.

## Responsiveness and release

- [ ] At widths 390, 768 and 1440 pixels, navigate all pages. Expected: no page-wide horizontal overflow; long tables scroll inside their cards; navigation remains usable.
- [ ] Use keyboard Tab and Enter through login, order entry and import confirmation. Expected: visible focus and labelled inputs.
- [ ] Run frontend lint/build, full backend pytest/ruff, browser smoke and k6. Expected: every command exits 0; no skipped PostgreSQL tests in the release run.
- [ ] Publish screenshots and video only after actually capturing them; record the real load-test result. Verify production cookies are Secure, demo mode is off and secrets differ from development values.
