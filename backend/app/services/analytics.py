from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Instrument, Portfolio, Snapshot
from app.services import market
from app.services.accounting import ONE, ZERO, replay
from app.services.trading import ledger, owned_portfolio
from app.services.risk import risk_metrics, xirr


def portfolio_summary(db: Session, user_id: str, portfolio_id: str) -> dict:
    portfolio = owned_portfolio(db, user_id, portfolio_id)
    entries = ledger(db, portfolio_id)
    book = replay(entries)
    positions, allocation = [], {key: {} for key in ("stock", "sector", "market", "currency")}
    day_change, stale, demo = ZERO, False, False
    fx_payload = None
    for symbol, lots in book.lots.items():
        if not lots:
            continue
        instrument = db.get(Instrument, symbol)
        q = market.quote(db, symbol)
        if instrument.currency == "USD" and fx_payload is None:
            fx_payload = market.fx(db)
        rate = Decimal(fx_payload["price"]) if instrument.currency == "USD" else ONE
        previous_fx = Decimal(fx_payload["previous_close"]) if instrument.currency == "USD" else ONE
        p = book.position(symbol, Decimal(q["price"]), rate)
        change = p["value_inr"] - p["quantity"] * Decimal(q["previous_close"]) * previous_fx
        day_change += change
        positions.append({"symbol": symbol, "name": instrument.name, "sector": instrument.sector, "market": instrument.market, "currency": instrument.currency, **{k: str(v) for k, v in p.items()}, "price": q["price"], "day_change_inr": str(change), "stale": q["stale"], "demo": q["demo"], "as_of": q["as_of"], "provider": q["provider"]})
        for kind, label in (("stock", symbol), ("sector", instrument.sector), ("market", instrument.market), ("currency", instrument.currency)):
            allocation[kind][label] = allocation[kind].get(label, ZERO) + p["value_inr"]
        stale |= q["stale"]
        demo |= q["demo"]
    if fx_payload:
        stale |= fx_payload["stale"]
    invested = sum((Decimal(p["cost_inr"]) for p in positions), ZERO)
    holdings_value = sum((Decimal(p["value_inr"]) for p in positions), ZERO)
    unrealized = holdings_value - invested
    value = book.cash + holdings_value
    flows = [(e.created_at.date(), -e.cash_delta) for e in entries if e.kind == "DEPOSIT"]
    flows.append((date.today(), value))
    irr = xirr(flows) if portfolio.kind == "paper" else None
    return {"id": portfolio.id, "name": portfolio.name, "kind": portfolio.kind, "base_currency": "INR", "cash": str(book.cash), "holdings_value": str(holdings_value), "total_value": str(value), "cost_basis": str(invested), "day_change": str(day_change), "day_change_note": "Current holdings versus previous provider close; excludes intraday trade timing", "realized_pnl": str(book.realized), "unrealized_pnl": str(unrealized), "total_pnl": str(book.realized + unrealized), "xirr_pct": str(irr * 100) if irr is not None else None, "positions": positions, "allocation": {kind: [{"name": label, "value": str(v), "weight_pct": str(v / holdings_value * 100) if holdings_value else "0"} for label, v in group.items()] for kind, group in allocation.items()}, "stale": stale, "demo": demo, "fx": fx_payload, "import_note": "Imported average costs have no acquisition dates. Current FX approximates historical INR cost; XIRR is unavailable." if portfolio.kind == "import" else None}


def performance(db: Session, portfolio: Portfolio) -> dict:
    rows = list(db.scalars(select(Snapshot).where(Snapshot.portfolio_id == portfolio.id).order_by(Snapshot.day)))
    if not rows:
        return {"points": [], "volatility_pct": None, "max_drawdown_pct": None, "note": "Daily snapshots will appear after the background job runs."}
    first = rows[0]
    points = []
    for row in rows:
        points.append({"date": row.day.isoformat(), "value": str(row.value), "portfolio_index": str(row.value / first.value * 100) if first.value else None, "nifty_index": str(row.nifty / first.nifty * 100), "sp500_inr_index": str(row.sp500 * row.fx_rate / (first.sp500 * first.fx_rate) * 100), "stale": row.stale, "demo": row.demo})
    return {"points": points, **risk_metrics([r.value for r in rows]), "demo": any(r.demo for r in rows), "note": "Price-only Nifty 50 and S&P 500; US benchmark converted to INR. Normalized to 100 at the first common snapshot. No dividends or fees. Volatility assumes 252 trading days."}
