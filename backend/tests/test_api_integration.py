from decimal import Decimal

import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.db import get_db
from app.main import app
from app.services import cache, market

pytestmark = pytest.mark.integration


@pytest.fixture
def client(integration_engine, monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(cache, 'redis', fake)
    monkeypatch.setattr(market, 'redis', fake)
    factory = sessionmaker(integration_engine, expire_on_commit=False)
    def db_override():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = db_override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def register(client):
    from app.models.entities import uid
    result = client.post('/api/auth/register',json={'email':uid()+'@example.com','password':'A-strong-pass-2026'})
    assert result.status_code == 201, result.text
    return {'Authorization':'Bearer '+result.json()['access_token']}


def test_auth_rotation_csrf_replay_revokes_family(client):
    headers = register(client)
    assert client.get('/api/auth/me',headers=headers).status_code == 200
    old_refresh = client.cookies.get('gh_refresh')
    old_csrf = client.cookies.get('gh_csrf')
    assert client.post('/api/auth/refresh').status_code == 403
    result = client.post('/api/auth/refresh',headers={'Origin':get_settings().frontend_url,'X-CSRF-Token':old_csrf})
    assert result.status_code == 200
    assert client.cookies.get('gh_refresh') != old_refresh
    fresh_headers = {'Authorization':'Bearer '+result.json()['access_token']}
    client.cookies.clear()
    client.cookies.set('gh_refresh',old_refresh,path='/api/auth')
    client.cookies.set('gh_csrf',old_csrf,path='/')
    result = client.post('/api/auth/refresh',headers={'Origin':get_settings().frontend_url,'X-CSRF-Token':old_csrf})
    assert result.status_code == 401
    assert client.get('/api/auth/me',headers=fresh_headers).status_code == 401


def test_login_never_accepts_wrong_password(client):
    register(client)
    bad = client.post('/api/auth/login',json={'email':'nobody@example.com','password':'Still-a-long-password'})
    assert bad.status_code == 401
    assert bad.json()['detail'] == 'Invalid email or password'


def test_validation_does_not_echo_password(client):
    result = client.post('/api/auth/register',json={'email':'a@example.com','password':'secret'})
    assert result.status_code == 422
    assert 'secret' not in result.text


def test_csv_preview_requires_confirmation_and_is_idempotent(client, integration_engine):
    from app.models import Instrument
    with integration_engine.begin() as connection:
        from sqlalchemy.dialects.postgresql import insert
        connection.execute(insert(Instrument).values(symbol='AAPL',name='Apple',sector='Technology',market='NASDAQ',currency='USD',tradable=True).on_conflict_do_nothing())
    headers = register(client)
    before = len(client.get('/api/portfolios',headers=headers).json())
    data = b'symbol,quantity,average_price\nAAPL,2,100\n'
    result = client.post('/api/imports/preview',headers=headers,files={'file':('test.csv',data,'text/csv')})
    assert result.status_code == 200
    assert result.json()['valid']
    assert len(client.get('/api/portfolios',headers=headers).json()) == before
    key = result.json()['preview_id']
    original_fx = market.fx
    market.fx = lambda db:{'price':'84','stale':False}
    try:
        first = client.post('/api/imports/confirm',headers=headers,json={'preview_id':key})
        second = client.post('/api/imports/confirm',headers=headers,json={'preview_id':key})
    finally:
        market.fx = original_fx
    assert first.status_code == 200, first.text
    assert first.json()['portfolio_id'] == second.json()['portfolio_id']
    assert second.json()['replayed'] is True
    entries = client.get('/api/portfolios/'+first.json()['portfolio_id']+'/ledger',headers=headers).json()
    assert len(entries) == 1
    assert Decimal(entries[0]['cash_delta_inr']) == 0


def test_duplicate_and_unknown_import_symbols_rejected(client):
    headers = register(client)
    data = b'symbol,quantity,average_price\nNO-SUCH-SYMBOL,2,100\n'
    result = client.post('/api/imports/preview',headers=headers,files={'file':('bad.csv',data,'text/csv')})
    assert result.status_code == 200
    assert not result.json()['valid']
    assert result.json()['preview_id'] is None
