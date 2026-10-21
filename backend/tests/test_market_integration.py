import json

import fakeredis
import pytest
from sqlalchemy.orm import Session

from app.services import market, providers
from app.services.catalog import DEMO_PRICES

pytestmark = pytest.mark.integration


def test_fallback_cache_and_stale_last_value(integration_engine, account, monkeypatch):
    _, _, symbol = account
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(market, 'redis', fake)
    monkeypatch.setattr(market.settings, 'demo_mode', False)
    monkeypatch.setattr(market.settings, 'alpha_vantage_key', 'test-key')
    with Session(integration_engine) as db:
        row = market.instrument_or_404(db, symbol)
        row.alpha_symbol = symbol
        db.commit()
    calls = []
    def quote(provider, instrument):
        calls.append(provider)
        if provider == 'yahoo':
            raise providers.ProviderFailure('Unavailable')
        return {'symbol':symbol,'price':'100','previous_close':'99','currency':'INR','as_of':'2026-10-19T00:00:00+00:00','provider':provider,'demo':False,'stale':False}
    monkeypatch.setattr(providers, 'quote_from', quote)
    with Session(integration_engine) as db:
        assert market.quote(db,symbol)['provider'] == 'alpha'
        assert market.quote(db,symbol)['price'] == '100'
        assert calls == ['yahoo','alpha']
        fake.delete(f'live:quote:{symbol}')
        def fail(*args):
            raise providers.ProviderFailure('All down')
        monkeypatch.setattr(providers,'quote_from',fail)
        q = market.quote(db,symbol)
        assert q['stale'] is True
        assert q['price'] == '100'
        assert json.loads(fake.get(f'last:live:quote:{symbol}'))['stale'] is False


def test_demo_data_is_explicitly_labelled():
    for symbol in DEMO_PRICES:
        assert market.demo_payload(symbol,False)['demo'] is True
        assert market.demo_payload(symbol,True)['demo'] is True
