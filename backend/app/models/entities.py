import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric,
    String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def uid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    family: Mapped[str] = mapped_column(String(36), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class Portfolio(Base):
    __tablename__ = "portfolios"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(16), default="paper")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (CheckConstraint("kind IN ('paper','import')"),)


class Instrument(Base):
    __tablename__ = "instruments"
    symbol: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    sector: Mapped[str] = mapped_column(String(80))
    market: Mapped[str] = mapped_column(String(20))
    currency: Mapped[str] = mapped_column(String(3))
    tradable: Mapped[bool] = mapped_column(Boolean, default=True)
    alpha_symbol: Mapped[str | None] = mapped_column(String(40))
    twelve_symbol: Mapped[str | None] = mapped_column(String(40))


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    sequence: Mapped[int] = mapped_column(Integer)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolios.id"), index=True)
    kind: Mapped[str] = mapped_column(String(12))
    symbol: Mapped[str | None] = mapped_column(ForeignKey("instruments.symbol"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(28, 8), default=Decimal(0))
    price: Mapped[Decimal] = mapped_column(Numeric(), default=Decimal(0))
    fx_rate: Mapped[Decimal] = mapped_column(Numeric(), default=Decimal(1))
    cash_delta: Mapped[Decimal] = mapped_column(Numeric())
    idempotency_key: Mapped[str] = mapped_column(String(100))
    request_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        UniqueConstraint("portfolio_id", "idempotency_key"),
        UniqueConstraint("portfolio_id", "sequence"),
        CheckConstraint("kind IN ('DEPOSIT','BUY','SELL','IMPORT')"),
        CheckConstraint("quantity >= 0 AND price >= 0 AND fx_rate > 0"),
        CheckConstraint("(kind = 'BUY' AND cash_delta = -quantity * price * fx_rate) OR (kind = 'SELL' AND cash_delta = quantity * price * fx_rate) OR kind IN ('DEPOSIT','IMPORT')"),
        CheckConstraint("(kind = 'DEPOSIT' AND symbol IS NULL AND quantity = 0 AND cash_delta > 0) OR (kind IN ('BUY','SELL','IMPORT') AND symbol IS NOT NULL AND quantity > 0 AND price > 0)"),
        CheckConstraint("(kind = 'BUY' AND cash_delta < 0) OR (kind = 'SELL' AND cash_delta > 0) OR (kind = 'IMPORT' AND cash_delta = 0) OR kind = 'DEPOSIT'"),
    )


class QuoteRecord(Base):
    __tablename__ = "quote_records"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Snapshot(Base):
    __tablename__ = "snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolios.id"), index=True)
    day: Mapped[date] = mapped_column(Date)
    value: Mapped[Decimal] = mapped_column(Numeric())
    nifty: Mapped[Decimal] = mapped_column(Numeric())
    sp500: Mapped[Decimal] = mapped_column(Numeric())
    fx_rate: Mapped[Decimal] = mapped_column(Numeric())
    stale: Mapped[bool] = mapped_column(Boolean, default=False)
    demo: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("portfolio_id", "day"),)


class WatchItem(Base):
    __tablename__ = "watch_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    symbol: Mapped[str] = mapped_column(ForeignKey("instruments.symbol"))
    __table_args__ = (UniqueConstraint("user_id", "symbol"),)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    symbol: Mapped[str] = mapped_column(ForeignKey("instruments.symbol"))
    direction: Mapped[str] = mapped_column(String(5))
    target: Mapped[Decimal] = mapped_column(Numeric())
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("target > 0 AND direction IN ('above','below')"),)


class ImportPreview(Base):
    __tablename__ = "import_previews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    rows: Mapped[list] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    portfolio_id: Mapped[str | None] = mapped_column(ForeignKey("portfolios.id"))


class BrokerConnection(Base):
    __tablename__ = "broker_connections"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    encrypted_token: Mapped[str] = mapped_column(Text)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class NewsDocument(Base):
    __tablename__ = "news_documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    symbol: Mapped[str] = mapped_column(ForeignKey("instruments.symbol"), index=True)
    headline: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    embedding: Mapped[list | None] = mapped_column(Vector(1536))
    __table_args__ = (UniqueConstraint("symbol", "url"),)


class Forecast(Base):
    __tablename__ = "forecasts"
    symbol: Mapped[str] = mapped_column(ForeignKey("instruments.symbol"), primary_key=True)
    result: Mapped[dict] = mapped_column(JSON)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


Index("ix_ledger_order", LedgerEntry.portfolio_id, LedgerEntry.sequence)
