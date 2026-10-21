import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import quote

import httpx

from app.config import get_settings
from app.models import Instrument
from app.services.cache import BUDGET, metric, redis

settings = get_settings()


class ProviderFailure(Exception):
    pass


def request_json(provider: str, url: str, params: dict | None = None) -> dict:
    limits = {"yahoo": (settings.yahoo_per_minute, settings.yahoo_per_day), "alpha": (5, 25), "twelve": (8, 800)}
    minute, day = limits[provider]
    now = int(time.time())
    allowed = redis.eval(BUDGET, 2, f"budget:{provider}:m:{now // 60}", f"budget:{provider}:d:{now // 86400}", minute, day)
    if not allowed:
        metric(f"budget_denied:{provider}")
        raise ProviderFailure("Local quota reached")
    metric(f"provider_calls:{provider}")
    try:
        with httpx.Client(timeout=5, follow_redirects=False) as client:
            response = client.get(url, params=params, headers={"User-Agent": "GrowHike/1.0 educational portfolio"})
            response.raise_for_status()
            result = json.loads(response.text, parse_float=Decimal)
            if not isinstance(result, dict):
                raise ValueError("Unexpected response")
            return result
    except (httpx.HTTPError, ValueError) as exc:
        raise ProviderFailure("Provider unavailable") from exc


def positive(value) -> Decimal:
    number = Decimal(str(value))
    if not number.is_finite() or number <= 0 or number > Decimal("1000000000000") or len(number.as_tuple().digits) > 22 or number.as_tuple().exponent < -12:
        raise ProviderFailure("Invalid price")
    return number


def quote_from(provider: str, instrument: Instrument) -> dict:
    if provider == "yahoo":
        data = request_json("yahoo", f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(instrument.symbol, safe='')}", {"range": "5d", "interval": "1d"})
        row = data["chart"]["result"][0]
        meta = row["meta"]
        if meta.get("currency") != instrument.currency:
            raise ProviderFailure("Currency mismatch")
        price = positive(meta["regularMarketPrice"])
        closes = [c for c in row["indicators"]["quote"][0]["close"] if c is not None]
        previous = positive(meta.get("previousClose") or (closes[-2] if len(closes) >= 2 else price))
        when = datetime.fromtimestamp(int(meta["regularMarketTime"]), timezone.utc).isoformat()
    elif provider == "alpha":
        if not settings.alpha_vantage_key or not instrument.alpha_symbol:
            raise ProviderFailure("Not configured")
        data = request_json("alpha", "https://www.alphavantage.co/query", {"function": "GLOBAL_QUOTE", "symbol": instrument.alpha_symbol, "apikey": settings.alpha_vantage_key})
        q = data["Global Quote"]
        if q["01. symbol"].upper() != instrument.alpha_symbol.upper():
            raise ProviderFailure("Symbol mismatch")
        price, previous = positive(q["05. price"]), positive(q["08. previous close"])
        when = q["07. latest trading day"] + "T00:00:00+00:00"
    else:
        if not settings.twelve_data_key or not instrument.twelve_symbol:
            raise ProviderFailure("Not configured")
        data = request_json("twelve", "https://api.twelvedata.com/quote", {"symbol": instrument.twelve_symbol, "apikey": settings.twelve_data_key})
        if data.get("currency", instrument.currency) != instrument.currency:
            raise ProviderFailure("Currency mismatch")
        price, previous = positive(data["close"]), positive(data.get("previous_close", data["close"]))
        when = datetime.fromtimestamp(int(data["timestamp"]), timezone.utc).isoformat()
    return {"symbol": instrument.symbol, "price": str(price), "previous_close": str(previous), "currency": instrument.currency, "as_of": when, "provider": provider, "demo": False, "stale": False}


def history_from(provider: str, instrument: Instrument) -> list[dict]:
    if provider == "yahoo":
        data = request_json("yahoo", f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(instrument.symbol, safe='')}", {"range": "2y", "interval": "1d"})
        row = data["chart"]["result"][0]
        if row["meta"].get("currency") != instrument.currency:
            raise ProviderFailure("Currency mismatch")
        # Use unadjusted closing prices consistently; total-return/corporate-action modelling is separate.
        return [{"date": datetime.fromtimestamp(int(t), timezone.utc).date().isoformat(), "close": str(positive(c))} for t, c in zip(row["timestamp"], row["indicators"]["quote"][0]["close"], strict=True) if c is not None]
    if provider == "alpha":
        if not settings.alpha_vantage_key or not instrument.alpha_symbol:
            raise ProviderFailure("Not configured")
        data = request_json("alpha", "https://www.alphavantage.co/query", {"function": "TIME_SERIES_DAILY", "symbol": instrument.alpha_symbol, "outputsize": "compact", "apikey": settings.alpha_vantage_key})
        return [{"date": day, "close": str(positive(v["4. close"]))} for day, v in sorted(data["Time Series (Daily)"].items())]
    if not settings.twelve_data_key or not instrument.twelve_symbol:
        raise ProviderFailure("Not configured")
    data = request_json("twelve", "https://api.twelvedata.com/time_series", {"symbol": instrument.twelve_symbol, "interval": "1day", "outputsize": 500, "apikey": settings.twelve_data_key})
    if data.get("meta", {}).get("currency", instrument.currency) != instrument.currency:
        raise ProviderFailure("Currency mismatch")
    return [{"date": v["datetime"][:10], "close": str(positive(v["close"]))} for v in reversed(data["values"])]


def fx_from(provider: str) -> dict:
    """Alpha FX uses the FX endpoint, never an incorrectly mapped stock symbol."""
    if provider == "alpha":
        if not settings.alpha_vantage_key:
            raise ProviderFailure("Not configured")
        data = request_json("alpha", "https://www.alphavantage.co/query", {"function": "CURRENCY_EXCHANGE_RATE", "from_currency": "USD", "to_currency": "INR", "apikey": settings.alpha_vantage_key})["Realtime Currency Exchange Rate"]
        value = positive(data["5. Exchange Rate"])
        return {"symbol": "INR=X", "price": str(value), "previous_close": str(value), "currency": "INR", "as_of": data["6. Last Refreshed"].replace(" ", "T") + "+00:00", "provider": provider, "demo": False, "stale": False}
    instrument = Instrument(symbol="INR=X", name="USD INR", currency="INR", market="FX", sector="FX", twelve_symbol="USD/INR")
    return quote_from(provider, instrument)
