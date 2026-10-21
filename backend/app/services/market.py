import json
import logging
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException
from redis.exceptions import RedisError
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Instrument, QuoteRecord
from app.db import cache_engine_for
from app.services import providers
from app.services.cache import lease, metric, redis
from app.services.catalog import DEMO_PRICES

settings = get_settings()
logger = logging.getLogger(__name__)


def instrument_or_404(db: Session, symbol: str) -> Instrument:
    row = db.get(Instrument, symbol)
    if not row:
        raise HTTPException(404, "Symbol is not in the supported catalogue")
    return row


def demo_payload(symbol: str, history: bool) -> dict:
    price = Decimal(DEMO_PRICES[symbol])
    if history:
        today = datetime.now(timezone.utc).date()
        # Deterministic synthetic series. Never passed off as historical market performance.
        points = []
        for n in range(730):
            day = today - timedelta(days=729 - n)
            if day.weekday() < 5:
                factor = Decimal("0.86") + Decimal(n) / Decimal("5200") + Decimal((n * 17) % 23 - 11) / Decimal("1000")
                points.append({"date": day.isoformat(), "close": str(price * factor)})
        return {"symbol": symbol, "points": points, "provider": "demo", "demo": True, "stale": False}
    return {"symbol": symbol, "price": str(price), "previous_close": str(price * Decimal("0.99")), "currency": "USD" if symbol in {"AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "TSLA", "JPM", "KO", "^GSPC"} else "INR", "as_of": datetime.now(timezone.utc).isoformat(), "provider": "demo", "demo": True, "stale": False}


def get_data(db: Session, symbol: str, history: bool = False) -> dict:
    instrument = instrument_or_404(db, symbol)
    prefix = "demo" if settings.demo_mode else "live"
    key = f"{prefix}:{'history' if history else 'quote'}:{symbol}"
    ttl = 3600 if history else (21600 if symbol == "INR=X" else settings.quote_ttl)
    metric("market_requests")
    try:
        cached = redis.get(key)
        if cached:
            metric("cache_hits")
            return json.loads(cached)
    except RedisError:
        return last_value(db, key)
    metric("cache_misses")
    try:
        with lease(f"lock:{key}", 25) as acquired:
            if not acquired:
                # Let the single cache owner finish. Subsequent callers do not spend API credits.
                for _ in range(10):
                    time.sleep(0.05)
                    if cached := redis.get(key):
                        metric("coalesced_requests")
                        return json.loads(cached)
                return last_value(db, key)
            if settings.demo_mode:
                payload = demo_payload(symbol, history)
            else:
                payload = None
                for provider in ("yahoo", "alpha", "twelve"):
                    if provider == "alpha" and (not settings.alpha_vantage_key or (symbol != "INR=X" and not instrument.alpha_symbol)):
                        continue
                    if provider == "twelve" and (not settings.twelve_data_key or not instrument.twelve_symbol):
                        continue
                    try:
                        if history:
                            points = providers.history_from(provider, instrument)
                            if len(points) < 2:
                                raise providers.ProviderFailure("Insufficient history")
                            payload = {"symbol": symbol, "points": points, "provider": provider, "demo": False, "stale": False}
                        else:
                            payload = providers.fx_from(provider) if symbol == "INR=X" else providers.quote_from(provider, instrument)
                        break
                    except (providers.ProviderFailure, KeyError, TypeError, ValueError, IndexError, ArithmeticError):
                        metric(f"provider_failures:{provider}")
                if payload is None:
                    return last_value(db, key)
            payload["fetched_at"] = datetime.now(timezone.utc).isoformat()
            # An isolated DB transaction never commits the caller's order/import transaction.
            with Session(cache_engine_for(db.get_bind().url)) as cache_db:
                cache_db.execute(insert(QuoteRecord).values(key=key, payload=payload).on_conflict_do_update(index_elements=[QuoteRecord.key], set_={"payload": payload, "fetched_at": datetime.now(timezone.utc)}))
                cache_db.commit()
            redis.set(key, json.dumps(payload), ex=ttl)
            redis.set(f"last:{key}", json.dumps(payload), ex=settings.stale_seconds)
            return payload
    except RedisError:
        return last_value(db, key)


def last_value(db: Session, key: str) -> dict:
    cached = None
    try:
        cached = redis.get(f"last:{key}")
    except RedisError:
        pass
    row = db.get(QuoteRecord, key) if not cached else None
    payload = json.loads(cached) if cached else (dict(row.payload) if row else None)
    if payload:
        payload["stale"] = True
        payload["stale_reason"] = "Provider or cache unavailable; displaying last known value"
        metric("stale_served")
        return payload
    raise HTTPException(503, "No cached market data available. Try later or enable demo mode.")


def quote(db: Session, symbol: str) -> dict:
    return get_data(db, symbol)


def history(db: Session, symbol: str) -> dict:
    return get_data(db, symbol, True)


def fx(db: Session) -> dict:
    return quote(db, "INR=X")


def news(db: Session, symbol: str) -> dict:
    """News uses this same gateway, request budgets and last-value policy."""
    instrument_or_404(db, symbol)
    if settings.demo_mode:
        return {"news": [], "demo": True, "stale": False}
    key = f"live:news:{symbol}"
    metric("market_requests")
    try:
        if cached := redis.get(key):
            metric("cache_hits")
            return json.loads(cached)
        metric("cache_misses")
        with lease(f"lock:{key}", 20) as acquired:
            if not acquired:
                return last_value(db, key)
            try:
                data = providers.request_json("yahoo", "https://query1.finance.yahoo.com/v1/finance/search", {"q": symbol, "quotesCount": 0, "newsCount": 6})
                rows = data.get("news", [])[:6]
                payload = {"news": rows, "provider": "yahoo", "stale": False, "demo": False, "fetched_at": datetime.now(timezone.utc).isoformat()}
                # Parse-float Decimal values from unrelated provider fields are not retained.
                payload["news"] = [{"title": str(r["title"]), "link": str(r["link"]), "providerPublishTime": int(r["providerPublishTime"])} for r in rows]
                with Session(cache_engine_for(db.get_bind().url)) as cache_db:
                    cache_db.execute(insert(QuoteRecord).values(key=key, payload=payload).on_conflict_do_update(index_elements=[QuoteRecord.key], set_={"payload": payload, "fetched_at": datetime.now(timezone.utc)}))
                    cache_db.commit()
                redis.set(key, json.dumps(payload), ex=3600)
                redis.set(f"last:{key}", json.dumps(payload), ex=settings.stale_seconds)
                return payload
            except (providers.ProviderFailure, KeyError, TypeError, ValueError):
                metric("provider_failures:yahoo")
                return last_value(db, key)
    except RedisError:
        return last_value(db, key)
