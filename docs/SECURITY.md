# Security decisions

- Passwords use bcrypt with cost 12. Inputs are limited to 72 UTF-8 bytes, avoiding silent bcrypt truncation. Wrong-user and wrong-password errors use the same message.
- Access JWTs expire in ten minutes and require issuer, audience, subject, session family, expiry and issue time. A session lookup enables immediate family revocation. The identity lookup releases its database connection before a long SSE response starts.
- Refresh tokens are opaque random values. Only their SHA-256 hashes are stored in PostgreSQL. Rotation preserves a session family; replay revokes that family. Independent sessions remain independent.
- The browser keeps access tokens in memory. Refresh cookies are httpOnly, SameSite=Lax and Secure in production. The readable CSRF cookie must match the request header and stored session hash; refresh/logout require the allowed Origin. HTTP development cookies are for localhost only.
- Refresh requests are coalesced within a tab and serialized with Web Locks across supported browser tabs. Unsupported browsers still have per-tab coordination.
- Login limits use atomic Redis counters for both IP and hashed account identity. Redis failure fails authentication closed. Deployment proxies must be configured with the correct trusted client-IP chain before public use; do not trust arbitrary incoming forwarded headers.
- Google uses a browser-bound state cookie, a one-time Redis state record, PKCE, nonce, a verified signed ID token, audience/issuer checks and a verified email flag. An existing password account is not automatically linked by email.
- Every private portfolio/preview lookup checks the owner. Mutations require bearer authentication. Orders cannot accept a browser-provided fill price.
- The portfolio row lock serializes trading writers. Idempotency is checked after taking that lock and is also protected by a unique constraint. SQL constraints enforce cash-movement math and signs. Ledger and audit rows reject update/delete/truncate.
- All live data use one backend gateway, with Redis request budgets and cache locks. Cache failure does not trigger a free-for-all of upstream requests. The persistent last value is labelled stale and cannot fund a new trade.
- SQLAlchemy parameter values are hidden from database exceptions. HTTP logs exclude query strings, headers, credentials and bodies. External HTTP client request logging is disabled because provider API keys can occur in query strings.
- Uploaded files are bounded before multipart parsing, parsed in memory/temporary upload handling, and closed after reading. XLSX expanded size is capped and external links are not retained. Formula execution is not supported. Only validated rows are persisted in preview records.
- Broker tokens use authenticated Fernet encryption with a separate environment key. Losing the key requires reconnection; the database alone is insufficient to decrypt tokens. Disconnect removes local token storage and does not promise broker-side grant revocation.
- News URLs must be HTTPS. The model never supplies the source URLs rendered by the UI. Headlines are untrusted data in the prompt; citation IDs are checked, and invalid generation falls back to original headlines. This does not prove that every generated sentence is true, so the UI links the underlying evidence.
- Production configuration rejects development JWT secrets, insecure cookies, missing encryption keys and enabled demo mode. The seeded shared demo user cannot authenticate when demo mode is disabled.

The supplied tests and safeguards need the full acceptance run before public deployment. This project does not claim a penetration test, exchange data entitlement, compliance certification, production hardening review, or financial predictive accuracy.
