import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.schemas.requests import Credentials, OrderRequest
from app.services.security import password_hash, verify_password


def test_bcrypt_hash_and_wrong_password():
    hashed = password_hash("a-long-enough-password")
    assert hashed != "a-long-enough-password"
    assert verify_password("a-long-enough-password", hashed)
    assert not verify_password("wrong-but-long-password", hashed)
    assert not verify_password("wrong-but-long-password", None)


@pytest.mark.parametrize("quantity", ["0", "-1", "NaN", "Infinity", "0.000000001"])
def test_invalid_order_quantities(quantity):
    with pytest.raises(ValidationError):
        OrderRequest(symbol="AAPL", side="BUY", quantity=quantity)


def test_multibyte_password_is_not_silently_truncated():
    with pytest.raises(ValidationError):
        Credentials(email="a@example.com", password="🌄"*30)


def test_rate_limit_is_atomic_and_has_ttl(monkeypatch):
    import fakeredis
    from app.services import cache
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(cache, "redis", fake)
    cache.limit("test", "person", 1, 60)
    with pytest.raises(HTTPException) as e:
        cache.limit("test", "person", 1, 60)
    assert e.value.status_code == 429
    assert 0 < fake.ttl(next(iter(fake.scan_iter("rate:*")))) <= 60


def test_distributed_budget_enforces_minute_and_day():
    import fakeredis
    from app.services.cache import BUDGET
    fake = fakeredis.FakeRedis(decode_responses=True)
    assert fake.eval(BUDGET, 2, "m", "d", 1, 2) == 1
    assert fake.eval(BUDGET, 2, "m", "d", 1, 2) == 0
    assert fake.eval(BUDGET, 2, "m2", "d", 1, 2) == 1
    assert fake.eval(BUDGET, 2, "m3", "d", 1, 2) == 0


def test_json_float_amounts_are_rejected_in_favour_of_decimal_strings():
    with pytest.raises(ValidationError):
        OrderRequest(symbol='AAPL',side='BUY',quantity=0.1)
    assert str(OrderRequest(symbol='AAPL',side='BUY',quantity='0.1').quantity) == '0.1'
