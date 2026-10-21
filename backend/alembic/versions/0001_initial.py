"""Initial PostgreSQL schema, vector extension and immutable accounting tables."""
from alembic import context, op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE users (
 id varchar(36) PRIMARY KEY, email varchar(254) NOT NULL UNIQUE,
 is_demo boolean NOT NULL, password_hash varchar(255), google_sub varchar(255) UNIQUE, created_at timestamptz NOT NULL
);
CREATE TABLE refresh_tokens (
 id varchar(36) PRIMARY KEY, user_id varchar(36) NOT NULL REFERENCES users(id),
 family varchar(36) NOT NULL, token_hash varchar(64) NOT NULL UNIQUE,
 csrf_hash varchar(64) NOT NULL, expires_at timestamptz NOT NULL, revoked boolean NOT NULL
);
CREATE INDEX ix_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX ix_refresh_tokens_family ON refresh_tokens(family);
CREATE TABLE portfolios (
 id varchar(36) PRIMARY KEY, user_id varchar(36) NOT NULL REFERENCES users(id),
 name varchar(100) NOT NULL, kind varchar(16) NOT NULL CHECK(kind IN ('paper','import')), created_at timestamptz NOT NULL
);
CREATE INDEX ix_portfolios_user_id ON portfolios(user_id);
CREATE TABLE instruments (
 symbol varchar(40) PRIMARY KEY, name varchar(150) NOT NULL, sector varchar(80) NOT NULL,
 market varchar(20) NOT NULL, currency varchar(3) NOT NULL, tradable boolean NOT NULL,
 alpha_symbol varchar(40), twelve_symbol varchar(40)
);
CREATE TABLE ledger_entries (
 id varchar(36) PRIMARY KEY, sequence integer NOT NULL,
 portfolio_id varchar(36) NOT NULL REFERENCES portfolios(id), kind varchar(12) NOT NULL,
 symbol varchar(40) REFERENCES instruments(symbol), quantity numeric(28,8) NOT NULL,
 price numeric NOT NULL, fx_rate numeric NOT NULL, cash_delta numeric NOT NULL,
 idempotency_key varchar(100) NOT NULL, request_hash varchar(64) NOT NULL, created_at timestamptz NOT NULL,
 UNIQUE(portfolio_id,idempotency_key), UNIQUE(portfolio_id,sequence),
 CHECK(kind IN ('DEPOSIT','BUY','SELL','IMPORT')),
 CHECK(quantity >= 0 AND price >= 0 AND fx_rate > 0),
 CHECK((kind='BUY' AND cash_delta=-quantity*price*fx_rate) OR (kind='SELL' AND cash_delta=quantity*price*fx_rate) OR kind IN ('DEPOSIT','IMPORT')),
 CHECK((kind = 'DEPOSIT' AND symbol IS NULL AND quantity = 0 AND cash_delta > 0) OR
       (kind IN ('BUY','SELL','IMPORT') AND symbol IS NOT NULL AND quantity > 0 AND price > 0)),
 CHECK((kind = 'BUY' AND cash_delta < 0) OR (kind = 'SELL' AND cash_delta > 0) OR
       (kind = 'IMPORT' AND cash_delta = 0) OR kind = 'DEPOSIT')
);
CREATE INDEX ix_ledger_entries_portfolio_id ON ledger_entries(portfolio_id);
CREATE INDEX ix_ledger_order ON ledger_entries(portfolio_id,sequence);
CREATE TABLE quote_records (key varchar(100) PRIMARY KEY, payload json NOT NULL, fetched_at timestamptz NOT NULL);
CREATE TABLE snapshots (
 id varchar(36) PRIMARY KEY, portfolio_id varchar(36) NOT NULL REFERENCES portfolios(id), day date NOT NULL,
 value numeric NOT NULL, nifty numeric NOT NULL, sp500 numeric NOT NULL,
 fx_rate numeric NOT NULL, stale boolean NOT NULL, demo boolean NOT NULL, UNIQUE(portfolio_id,day)
);
CREATE INDEX ix_snapshots_portfolio_id ON snapshots(portfolio_id);
CREATE TABLE watch_items (
 id varchar(36) PRIMARY KEY, user_id varchar(36) NOT NULL REFERENCES users(id), symbol varchar(40) NOT NULL REFERENCES instruments(symbol), UNIQUE(user_id,symbol)
);
CREATE INDEX ix_watch_items_user_id ON watch_items(user_id);
CREATE TABLE alerts (
 id varchar(36) PRIMARY KEY, user_id varchar(36) NOT NULL REFERENCES users(id), symbol varchar(40) NOT NULL REFERENCES instruments(symbol),
 direction varchar(5) NOT NULL, target numeric NOT NULL, triggered_at timestamptz,
 CHECK(target > 0 AND direction IN ('above','below'))
);
CREATE INDEX ix_alerts_user_id ON alerts(user_id);
CREATE TABLE import_previews (
 id varchar(36) PRIMARY KEY, user_id varchar(36) NOT NULL REFERENCES users(id), name varchar(100) NOT NULL,
 rows json NOT NULL, expires_at timestamptz NOT NULL, portfolio_id varchar(36) REFERENCES portfolios(id)
);
CREATE INDEX ix_import_previews_user_id ON import_previews(user_id);
CREATE TABLE broker_connections (
 user_id varchar(36) PRIMARY KEY REFERENCES users(id), encrypted_token text NOT NULL, connected_at timestamptz NOT NULL
);
CREATE TABLE news_documents (
 id varchar(36) PRIMARY KEY, symbol varchar(40) NOT NULL REFERENCES instruments(symbol),
 headline varchar(500) NOT NULL, url text NOT NULL, published_at timestamptz NOT NULL, embedding vector(1536), UNIQUE(symbol,url)
);
CREATE INDEX ix_news_documents_symbol ON news_documents(symbol);
CREATE TABLE forecasts (symbol varchar(40) PRIMARY KEY REFERENCES instruments(symbol), result json NOT NULL, trained_at timestamptz NOT NULL);
CREATE TABLE audit_events (
 id varchar(36) PRIMARY KEY, user_id varchar(36) REFERENCES users(id), action varchar(80) NOT NULL, entity_id varchar(80), created_at timestamptz NOT NULL
);
CREATE INDEX ix_audit_events_user_id ON audit_events(user_id);
CREATE FUNCTION reject_accounting_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Accounting and audit history are append-only'; END;
$$;
CREATE TRIGGER immutable_ledger BEFORE UPDATE OR DELETE ON ledger_entries FOR EACH ROW EXECUTE FUNCTION reject_accounting_mutation();
CREATE TRIGGER immutable_ledger_truncate BEFORE TRUNCATE ON ledger_entries FOR EACH STATEMENT EXECUTE FUNCTION reject_accounting_mutation();
CREATE TRIGGER immutable_audit BEFORE UPDATE OR DELETE ON audit_events FOR EACH ROW EXECUTE FUNCTION reject_accounting_mutation();
CREATE TRIGGER immutable_audit_truncate BEFORE TRUNCATE ON audit_events FOR EACH STATEMENT EXECUTE FUNCTION reject_accounting_mutation();
"""


def upgrade():
    if context.is_offline_mode():
        op.execute(SCHEMA)
    else:
        # Use the simple protocol for multi-statement SQL, within Alembic's transaction.
        with op.get_bind().connection.driver_connection.cursor() as cursor:
            cursor.execute(SCHEMA, prepare=False)


def downgrade():
    raise RuntimeError("Destructive downgrade disabled: restore a backup or explicitly recreate a development database")
