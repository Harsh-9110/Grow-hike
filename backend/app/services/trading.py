import hashlib
import json
from decimal import Decimal, localcontext

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent, LedgerEntry, Portfolio
from app.schemas.requests import OrderRequest
from app.services import market
from app.services.accounting import ZERO, replay


def owned_portfolio(db: Session, user_id: str, portfolio_id: str, lock: bool = False) -> Portfolio:
    stmt = select(Portfolio).where(Portfolio.id == portfolio_id, Portfolio.user_id == user_id)
    if lock:
        stmt = stmt.with_for_update()
    row = db.scalar(stmt)
    if not row:
        raise HTTPException(404, "Portfolio not found")
    return row


def ledger(db: Session, portfolio_id: str) -> list[LedgerEntry]:
    return list(db.scalars(select(LedgerEntry).where(LedgerEntry.portfolio_id == portfolio_id).order_by(LedgerEntry.sequence)))


def entry_dict(row: LedgerEntry) -> dict:
    return {"id": row.id, "sequence": row.sequence, "kind": row.kind, "symbol": row.symbol, "quantity": str(row.quantity), "price": str(row.price), "fx_rate": str(row.fx_rate), "cash_delta_inr": str(row.cash_delta), "created_at": row.created_at.isoformat()}


def execute_order(db: Session, user_id: str, portfolio_id: str, order: OrderRequest, key: str) -> dict:
    # Fetch network data before taking a DB row lock; slow APIs cannot hold the account hostage.
    instrument = market.instrument_or_404(db, order.symbol)
    if not instrument.tradable:
        raise HTTPException(422, "Indices and FX cannot be traded")
    # Canonical quantity means retries with '1' and '1.0' have the same request fingerprint.
    fingerprint = hashlib.sha256(json.dumps({"symbol": order.symbol, "side": order.side, "quantity": str(order.quantity.normalize())}, sort_keys=True).encode()).hexdigest()
    owned_portfolio(db, user_id, portfolio_id)
    old = db.scalar(select(LedgerEntry).where(LedgerEntry.portfolio_id == portfolio_id, LedgerEntry.idempotency_key == key))
    if old:
        if old.request_hash != fingerprint:
            raise HTTPException(409, "This idempotency key was used for a different order")
        return {"entry": entry_dict(old), "replayed": True}
    q = market.quote(db, order.symbol)
    f = market.fx(db) if instrument.currency == "USD" else {"price": "1", "stale": False, "demo": q["demo"]}
    if q["stale"] or f["stale"]:
        raise HTTPException(409, "Trading is paused while prices or FX are stale")
    # READ COMMITTED + the parent row lock serialize every writer for this portfolio.
    portfolio = owned_portfolio(db, user_id, portfolio_id, lock=True)
    if portfolio.kind != "paper":
        raise HTTPException(403, "Imported portfolios are read-only")
    entries = ledger(db, portfolio.id)
    old = next((e for e in entries if e.idempotency_key == key), None)
    if old:
        if old.request_hash != fingerprint:
            raise HTTPException(409, "This idempotency key was used for a different order")
        return {"entry": entry_dict(old), "replayed": True}
    with localcontext() as ctx:
        ctx.prec = 120
        book = replay(entries)
        price, rate = Decimal(q["price"]), Decimal(f["price"])
        cost = order.quantity * price * rate
        if order.side == "BUY" and cost > book.cash:
            raise HTTPException(409, "Insufficient virtual cash")
        held = sum((lot.quantity for lot in book.lots[order.symbol]), ZERO)
        if order.side == "SELL" and order.quantity > held:
            raise HTTPException(409, "Insufficient shares; short selling is disabled")
        row = LedgerEntry(portfolio_id=portfolio.id, sequence=len(entries) + 1, kind=order.side, symbol=order.symbol, quantity=order.quantity, price=price, fx_rate=rate, cash_delta=-cost if order.side == "BUY" else cost, idempotency_key=key, request_hash=fingerprint)
        db.add(row)
        db.flush()
        db.add(AuditEvent(user_id=user_id, action="paper_order", entity_id=row.id))
        db.commit()
        return {"entry": entry_dict(row), "replayed": False, "demo": q["demo"]}
