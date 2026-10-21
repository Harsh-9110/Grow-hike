import os

import pytest


@pytest.fixture(scope="session")
def integration_engine():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to run real PostgreSQL integration tests")
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url
    if make_url(url).database != "grow_test":
        raise RuntimeError("Integration tests are restricted to grow_test")
    engine = create_engine(url, pool_size=10, max_overflow=10)
    yield engine
    engine.dispose()


@pytest.fixture
def account(integration_engine):
    from decimal import Decimal
    from sqlalchemy.orm import Session
    from app.models import Instrument, LedgerEntry, Portfolio, User
    from app.models.entities import uid
    with Session(integration_engine, expire_on_commit=False) as db:
        symbol = "T" + uid()[:8].upper() + ".NS"
        db.add(Instrument(symbol=symbol, name="Test stock", sector="Test", market="NSE", currency="INR", tradable=True))
        user = User(email=uid()+"@example.com")
        db.add(user)
        db.flush()
        portfolio = Portfolio(user_id=user.id, name="Test", kind="paper")
        db.add(portfolio)
        db.flush()
        db.add(LedgerEntry(portfolio_id=portfolio.id, sequence=1, kind="DEPOSIT", quantity=Decimal(0), price=Decimal(0), fx_rate=Decimal(1), cash_delta=Decimal("150"), idempotency_key="deposit", request_hash="deposit"))
        db.commit()
        return user.id, portfolio.id, symbol
