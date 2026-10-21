import asyncio
import json
from decimal import Decimal
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from redis.exceptions import RedisError
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.db import SessionLocal, get_db
from app.models import Alert, Forecast, Portfolio, RefreshToken, User, WatchItem
from app.models.entities import utcnow
from app.schemas.requests import AlertRequest, ImportConfirm, IPORequest, OrderRequest, SymbolRequest
from app.services import imports, market
from app.services.analytics import performance, portfolio_summary
from app.services.cache import lease, limit, redis
from app.services.insights import summarize
from app.services.security import bearer, current_user
from app.services.trading import entry_dict, execute_order, ledger, owned_portfolio

router = APIRouter()
settings = get_settings()


@router.get("/config", tags=["Configuration"])
def config():
    return {"demo_mode": settings.demo_mode, "google_enabled": bool(settings.google_client_id and settings.google_client_secret), "broker_enabled": bool(settings.kite_api_key and settings.encryption_key), "demo_email": settings.demo_email if settings.demo_mode else None, "demo_password": settings.demo_password if settings.demo_mode else None}


@router.get("/stocks", tags=["Market"])
def stocks(q: str = Query("", max_length=80), db: Session = Depends(get_db), user: User = Depends(current_user)):
    from app.models import Instrument
    rows = db.scalars(select(Instrument).where(Instrument.tradable.is_(True)).order_by(Instrument.symbol))
    return [{"symbol": i.symbol, "name": i.name, "sector": i.sector, "market": i.market, "currency": i.currency} for i in rows if q.lower() in (i.symbol + " " + i.name).lower()]


@router.get("/stocks/{symbol}/quote", tags=["Market"])
def quote(symbol: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return market.quote(db, symbol)


@router.get("/stocks/{symbol}/history", tags=["Market"])
def history(symbol: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return market.history(db, symbol)


@router.get("/fx", tags=["Market"])
def fx(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return market.fx(db)


@router.get("/portfolios", tags=["Portfolio"])
def portfolios(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return [{"id": p.id, "name": p.name, "kind": p.kind} for p in db.scalars(select(Portfolio).where(Portfolio.user_id == user.id).order_by(Portfolio.created_at))]


@router.get("/portfolios/{portfolio_id}", tags=["Portfolio"])
def summary(portfolio_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return portfolio_summary(db, user.id, portfolio_id)


@router.get("/portfolios/{portfolio_id}/performance", tags=["Portfolio"])
def portfolio_performance(portfolio_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return performance(db, owned_portfolio(db, user.id, portfolio_id))


@router.get("/portfolios/{portfolio_id}/ledger", tags=["Paper trading"])
def transactions(portfolio_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    owned_portfolio(db, user.id, portfolio_id)
    return [entry_dict(e) for e in ledger(db, portfolio_id)]


@router.post("/portfolios/{portfolio_id}/orders", tags=["Paper trading"])
def order(portfolio_id: str, body: OrderRequest, idempotency_key: Annotated[str, Header(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_:\-]+$")], db: Session = Depends(get_db), user: User = Depends(current_user)):
    limit("orders", user.id, 60, 60)
    return execute_order(db, user.id, portfolio_id, body, idempotency_key)


@router.get("/watchlist", tags=["Watchlist and alerts"])
def watchlist(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [{"id": w.id, "symbol": w.symbol} for w in db.scalars(select(WatchItem).where(WatchItem.user_id == user.id))]


@router.post("/watchlist", tags=["Watchlist and alerts"])
def add_watch(body: SymbolRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    market.instrument_or_404(db, body.symbol)
    row = WatchItem(user_id=user.id, symbol=body.symbol)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
    return {"symbol": body.symbol}


@router.delete("/watchlist/{symbol}", status_code=204, tags=["Watchlist and alerts"])
def remove_watch(symbol: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(delete(WatchItem).where(WatchItem.user_id == user.id, WatchItem.symbol == symbol))
    db.commit()


@router.get("/alerts", tags=["Watchlist and alerts"])
def alerts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [{"id": a.id, "symbol": a.symbol, "direction": a.direction, "target": str(a.target), "triggered_at": a.triggered_at.isoformat() if a.triggered_at else None} for a in db.scalars(select(Alert).where(Alert.user_id == user.id))]


@router.post("/alerts", status_code=201, tags=["Watchlist and alerts"])
def add_alert(body: AlertRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    limit("alerts-create", user.id, 30, 3600)
    market.instrument_or_404(db, body.symbol)
    a = Alert(user_id=user.id, **body.model_dump())
    db.add(a)
    db.commit()
    return {"id": a.id}


@router.delete("/alerts/{alert_id}", status_code=204, tags=["Watchlist and alerts"])
def remove_alert(alert_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(delete(Alert).where(Alert.user_id == user.id, Alert.id == alert_id))
    db.commit()


@router.get("/metrics", tags=["Operations"])
def metrics(user: User = Depends(current_user)):
    values = {k: int(v) for k, v in redis.hgetall("metrics").items()}
    requests = values.get("market_requests", 0)
    hits = values.get("cache_hits", 0)
    durations = redis.lrange("request_times_us", 0, 999)
    times = sorted(int(t) for t in durations)
    return {"counters": values, "cache_hit_rate_pct": 100 * hits / requests if requests else 0, "api_calls_saved": hits + values.get("coalesced_requests", 0), "p50_ms": times[len(times)//2] / 1000 if times else 0, "p95_ms": times[min(len(times)-1, int(len(times)*0.95))] / 1000 if times else 0, "sample_size": len(times), "jobs": {"snapshots": redis.get("job:snapshot:last_success"), "alerts": redis.get("job:alerts:last_success"), "snapshot_errors": redis.get("job:snapshot:last_error")}, "note": "Shared counters since Redis reset. Latency: last 1,000 requests, excluding streaming duration. API calls saved counts hits and coalesced requests, not a billing estimate."}


@router.post("/imports/preview", tags=["Imports"])
async def import_preview(file: Annotated[UploadFile, File()], mapping: Annotated[str, Form()] = '{"symbol":"symbol","quantity":"quantity","average_price":"average_price"}', name: Annotated[str, Form(max_length=100)] = "Imported portfolio", db: Session = Depends(get_db), user: User = Depends(current_user)):
    limit("imports", user.id, 20, 3600)
    content = await file.read(imports.MAX_BYTES + 1)
    await file.close()
    try:
        parsed_mapping = json.loads(mapping)
        if not isinstance(parsed_mapping, dict) or set(parsed_mapping) != {"symbol", "quantity", "average_price"} or not all(isinstance(v, str) for v in parsed_mapping.values()) or len(set(parsed_mapping.values())) != 3:
            raise ValueError("Bad mapping")
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, "Map symbol, quantity, and average_price to header names") from exc
    rows = await run_in_threadpool(imports.read_rows, content, file.filename or "")
    return await run_in_threadpool(imports.preview, db, user.id, rows, parsed_mapping, name)


@router.post("/imports/confirm", tags=["Imports"])
def confirm_import(body: ImportConfirm, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return imports.confirm(db, user.id, body.preview_id)


@router.get("/insights/{symbol}", tags=["AI"])
def insights(symbol: str, question: str = Query("What do the latest headlines say?", max_length=300), user: User = Depends(current_user), db: Session = Depends(get_db)):
    limit("insights", user.id, 6, 3600)
    return summarize(db, symbol, question)


@router.get("/forecasts/{symbol}", tags=["Experimental ML"])
def forecast(symbol: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    market.instrument_or_404(db, symbol)
    row = db.get(Forecast, symbol)
    if row:
        return row.result
    q = market.quote(db, symbol)
    return {"status": "training_required", "demo": q["demo"], "forecasts": [{"horizon_sessions": h, "lstm": None, "naive": q["price"]} for h in [1, 3, 5]], "evaluation": [], "note": "No LSTM has been trained for this symbol. The naive baseline holds today's price constant. See README for the training command. Not financial advice."}


@router.post("/ipo/analyze", tags=["IPO"])
def ipo(body: IPORequest, user: User = Depends(current_user)):
    estimated = max(Decimal("0"), body.issue_price + body.gmp)
    return {"name": body.name, "issue_price": str(body.issue_price), "gmp": str(body.gmp), "gmp_pct": str(body.gmp / body.issue_price * 100), "estimated_listing": str(estimated), "subscription": str(body.subscription), "model": "Manual scenario: issue price + supplied GMP, floored at zero", "note": "Unregulated manual GMP input. This arithmetic scenario is not a validated predictive model or financial advice. Subscription is context only and does not affect this estimate."}


@router.get("/stream", tags=["Live cached quotes"])
async def stream(request: Request, symbols: str = Query("AAPL,RELIANCE.NS", max_length=400), auth: HTTPAuthorizationCredentials = Depends(bearer), user: User = Depends(current_user)):
    names = list(dict.fromkeys(symbols.split(",")))
    if len(names) > 8:
        raise HTTPException(422, "At most 8 symbols per stream")
    with SessionLocal() as db:
        for name in names:
            market.instrument_or_404(db, name)

    async def events():
        try:
            with lease(f"sse:{user.id}", 30) as acquired:
                if not acquired:
                    yield 'event: error\ndata: {"detail":"One stream per user is allowed"}\n\n'
                    return
                tick = 0
                while not await request.is_disconnected():
                    try:
                        claims = jwt.decode(auth.credentials, settings.jwt_secret, algorithms=["HS256"], issuer="grow-hike", audience="grow-hike-web")
                        with SessionLocal() as db:
                            active = db.scalar(select(RefreshToken.id).where(RefreshToken.family == claims["sid"], RefreshToken.revoked.is_(False), RefreshToken.expires_at > utcnow()).limit(1))
                            if not active:
                                break
                        await run_in_threadpool(redis.expire, f"sse:{user.id}", 30)
                    except (jwt.PyJWTError, RedisError):
                        yield 'event: expired\ndata: {}\n\n'
                        break
                    if tick % 4 == 0:
                        def quotes():
                            with SessionLocal() as db:
                                return [market.quote(db, name) for name in names]
                        try:
                            payload = await run_in_threadpool(quotes)
                            yield "event: quotes\ndata: " + json.dumps(payload) + "\n\n"
                        except HTTPException:
                            yield 'event: unavailable\ndata: {}\n\n'
                    else:
                        yield ": heartbeat\n\n"
                    tick += 1
                    await asyncio.sleep(15)
        except RedisError:
            yield 'event: unavailable\ndata: {}\n\n'
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
