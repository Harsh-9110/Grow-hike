from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.db import SessionLocal
from app.models import Instrument, LedgerEntry, Snapshot, User, WatchItem
from app.models.entities import utcnow
from app.routers.auth import create_paper_portfolio
from app.services.catalog import CATALOG
from app.services.security import password_hash


def seed():
    settings = get_settings()
    settings.validate_production()
    with SessionLocal() as db:
        # Serialize startup seeders, including a parallel CI API startup.
        db.execute(text("SELECT pg_advisory_xact_lock(478991)"))
        for symbol, name, sector, market, currency, alpha, twelve, _ in CATALOG:
            db.execute(insert(Instrument).values(symbol=symbol, name=name, sector=sector, market=market, currency=currency, tradable=sector not in ("FX", "Index"), alpha_symbol=alpha, twelve_symbol=twelve).on_conflict_do_nothing(index_elements=[Instrument.symbol]))
        if settings.demo_mode and not db.scalar(select(User).where(User.email == settings.demo_email)):
            user = User(email=settings.demo_email, is_demo=True, password_hash=password_hash(settings.demo_password))
            db.add(user)
            db.flush()
            portfolio = create_paper_portfolio(db, user.id)
            for n, (symbol, qty, price, fx) in enumerate([("RELIANCE.NS", "25", "1400", "1"), ("TCS.NS", "10", "3000", "1"), ("AAPL", "4", "210", "84"), ("NVDA", "6", "150", "84")], 2):
                q, p, f = Decimal(qty), Decimal(price), Decimal(fx)
                db.add(LedgerEntry(portfolio_id=portfolio.id, sequence=n, kind="BUY", symbol=symbol, quantity=q, price=p, fx_rate=f, cash_delta=-(q*p*f), idempotency_key=f"seed:{n}", request_hash="seed"))
            for symbol in ("RELIANCE.NS", "AAPL", "NVDA"):
                db.add(WatchItem(user_id=user.id, symbol=symbol))
            # Explicitly synthetic history; never claimed to be historical market performance.
            today = utcnow().date()
            for n in range(45):
                day = today - timedelta(days=45-n)
                if day.weekday() >= 5:
                    continue
                factor = Decimal("0.98") + Decimal(n) / Decimal("2500") + Decimal((n*7)%11) / Decimal("3000")
                db.add(Snapshot(portfolio_id=portfolio.id, day=day, value=Decimal("1023660")*factor, nifty=Decimal("25000")*factor, sp500=Decimal("6000")*(Decimal("0.99")+Decimal(n)/Decimal("4000")), fx_rate=Decimal("84"), stale=False, demo=True))
        db.commit()
    print("Catalogue ready. Demo user seeded only when DEMO_MODE=true.")


if __name__ == "__main__":
    seed()
