from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.models import LedgerEntry
from app.schemas.requests import OrderRequest
from app.services import market
from app.services.accounting import replay
from app.services.trading import execute_order, ledger

pytestmark = pytest.mark.integration


def fixed_quote(symbol, price="100"):
    return {"price": price, "symbol": symbol, "currency": "INR", "stale": False, "demo": True}


def test_two_concurrent_buys_only_one_can_spend_balance(integration_engine, account, monkeypatch):
    user_id, portfolio_id, symbol = account
    barrier = Barrier(2)
    def quote(db, name):
        barrier.wait(timeout=10)
        return fixed_quote(name)
    monkeypatch.setattr(market, "quote", quote)
    def buy(n):
        with Session(integration_engine, expire_on_commit=False) as db:
            try:
                execute_order(db, user_id, portfolio_id, OrderRequest(symbol=symbol, side="BUY", quantity="1"), f"concurrent-{n}")
                return 200
            except HTTPException as e:
                return e.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(buy, [1, 2]))
    assert sorted(results) == [200, 409]
    with Session(integration_engine) as db:
        rows = ledger(db, portfolio_id)
        assert len([e for e in rows if e.kind == "BUY"]) == 1
        assert replay(rows).cash == Decimal("50")
        assert replay(rows).position(symbol, Decimal("100"))["quantity"] == 1


def test_concurrent_same_key_is_a_single_fill(integration_engine, account, monkeypatch):
    user_id, portfolio_id, symbol = account
    barrier = Barrier(2)
    def quote(db, name):
        barrier.wait(timeout=10)
        return fixed_quote(name)
    monkeypatch.setattr(market, "quote", quote)
    def buy(_):
        with Session(integration_engine, expire_on_commit=False) as db:
            return execute_order(db, user_id, portfolio_id, OrderRequest(symbol=symbol, side="BUY", quantity="1"), "same-key-concurrent")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(buy, [1, 2]))
    assert sorted(r["replayed"] for r in results) == [False, True]
    assert results[0]["entry"]["id"] == results[1]["entry"]["id"]
    with Session(integration_engine) as db:
        assert len(ledger(db, portfolio_id)) == 2


def test_reused_key_different_body_conflicts(integration_engine, account, monkeypatch):
    user_id, portfolio_id, symbol = account
    monkeypatch.setattr(market, "quote", lambda db, s: fixed_quote(s))
    with Session(integration_engine, expire_on_commit=False) as db:
        execute_order(db, user_id, portfolio_id, OrderRequest(symbol=symbol, side="BUY", quantity="1"), "retry-key-one")
        with pytest.raises(HTTPException) as exc:
            execute_order(db, user_id, portfolio_id, OrderRequest(symbol=symbol, side="SELL", quantity="1"), "retry-key-one")
        assert exc.value.status_code == 409


def test_ledger_is_immutable_at_database_level(integration_engine, account):
    _, portfolio_id, _ = account
    with Session(integration_engine) as db:
        entry = db.scalar(select(LedgerEntry.id).where(LedgerEntry.portfolio_id == portfolio_id))
        with pytest.raises(DBAPIError):
            db.execute(text("UPDATE ledger_entries SET price=1 WHERE id=:id"), {"id": entry})
        db.rollback()
        with pytest.raises(DBAPIError):
            db.execute(text("DELETE FROM ledger_entries WHERE id=:id"), {"id": entry})
        db.rollback()


def test_stale_quote_and_short_sell_are_rejected(integration_engine, account, monkeypatch):
    user_id, portfolio_id, symbol = account
    monkeypatch.setattr(market, "quote", lambda db, s: {**fixed_quote(s), "stale": True})
    with Session(integration_engine) as db:
        with pytest.raises(HTTPException, match="") as exc:
            execute_order(db, user_id, portfolio_id, OrderRequest(symbol=symbol, side="BUY", quantity="1"), "stale-key")
        assert exc.value.status_code == 409
    monkeypatch.setattr(market, "quote", lambda db, s: fixed_quote(s))
    with Session(integration_engine) as db:
        with pytest.raises(HTTPException) as exc:
            execute_order(db, user_id, portfolio_id, OrderRequest(symbol=symbol, side="SELL", quantity="1"), "oversell-key")
        assert exc.value.status_code == 409


def test_other_user_cannot_trade_or_read_portfolio(integration_engine, account, monkeypatch):
    from app.models.entities import uid
    from app.services.trading import owned_portfolio
    _, portfolio_id, _unused_symbol = account
    with Session(integration_engine) as db:
        with pytest.raises(HTTPException) as exc:
            owned_portfolio(db, uid(), portfolio_id)
        assert exc.value.status_code == 404


def test_golden_sequence_through_real_order_transactions(integration_engine, account, monkeypatch):
    from app.services.trading import owned_portfolio
    user_id, portfolio_id, symbol = account
    with Session(integration_engine) as db:
        owned_portfolio(db,user_id,portfolio_id,lock=True)
        db.add(LedgerEntry(portfolio_id=portfolio_id,sequence=2,kind='DEPOSIT',quantity=Decimal(0),price=Decimal(0),fx_rate=Decimal(1),cash_delta=Decimal('10000'),idempotency_key='golden-deposit',request_hash='test'))
        db.commit()
    price = ['100']
    monkeypatch.setattr(market,'quote',lambda db,s:fixed_quote(s,price[0]))
    with Session(integration_engine,expire_on_commit=False) as db:
        execute_order(db,user_id,portfolio_id,OrderRequest(symbol=symbol,side='BUY',quantity='10'),'golden-buy-100')
        price[0]='120'
        execute_order(db,user_id,portfolio_id,OrderRequest(symbol=symbol,side='BUY',quantity='10'),'golden-buy-120')
        before = replay(ledger(db,portfolio_id)).position(symbol,Decimal('130'))
        assert before['average_cost'] == Decimal('110')
        assert before['unrealized'] == Decimal('400')
        assert before['return_pct'].quantize(Decimal('0.01')) == Decimal('18.18')
        price[0]='130'
        execute_order(db,user_id,portfolio_id,OrderRequest(symbol=symbol,side='SELL',quantity='15'),'golden-sell-130')
        book = replay(ledger(db,portfolio_id))
        p = book.position(symbol,Decimal('130'))
        assert book.realized == Decimal('350')
        assert p['quantity'] == Decimal('5')
        assert p['cost'] == Decimal('600')
        assert p['value'] == Decimal('650')
        assert p['unrealized'] == Decimal('50')
        assert book.realized+p['unrealized'] == Decimal('400')
