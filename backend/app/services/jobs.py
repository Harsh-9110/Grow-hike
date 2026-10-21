import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db import SessionLocal
from app.models import Alert, Portfolio, Snapshot
from app.models.entities import utcnow
from app.services import market
from app.services.analytics import portfolio_summary
from app.services.cache import lease, redis

logger = logging.getLogger(__name__)


def snapshot_job() -> None:
    with lease("job:snapshot", 3600) as acquired:
        if not acquired:
            return
        with SessionLocal() as db:
            # Daily observation at the configured time; this is not a global exchange close.
            day = datetime.now(ZoneInfo("Asia/Kolkata")).date()
            if day.weekday() >= 5:
                return
            failures = 0
            portfolios = list(db.scalars(select(Portfolio)))
            for portfolio in portfolios:
                try:
                    summary = portfolio_summary(db, portfolio.user_id, portfolio.id)
                    nifty, sp, fx = market.quote(db, "^NSEI"), market.quote(db, "^GSPC"), market.fx(db)
                    values = {"portfolio_id": portfolio.id, "day": day, "value": summary["total_value"], "nifty": nifty["price"], "sp500": sp["price"], "fx_rate": fx["price"], "stale": summary["stale"] or nifty["stale"] or sp["stale"] or fx["stale"], "demo": summary["demo"] or nifty["demo"]}
                    updates = {k: v for k, v in values.items() if k not in ("portfolio_id", "day")}
                    db.execute(insert(Snapshot).values(**values).on_conflict_do_update(index_elements=[Snapshot.portfolio_id, Snapshot.day], set_=updates))
                    db.commit()
                except Exception:
                    db.rollback()
                    failures += 1
                    logger.warning("snapshot_failed", extra={"event": "snapshot_failed"})
            redis.set("job:snapshot:last_error" if failures else "job:snapshot:last_success", utcnow().isoformat(), ex=345600)


def alerts_job() -> None:
    with lease("job:alerts", 55) as acquired:
        if not acquired:
            return
        with SessionLocal() as db:
            for alert in db.scalars(select(Alert).where(Alert.triggered_at.is_(None))):
                try:
                    q = market.quote(db, alert.symbol)
                    if q["stale"]:
                        continue
                    from decimal import Decimal
                    p = Decimal(q["price"])
                    if (alert.direction == "above" and p >= alert.target) or (alert.direction == "below" and p <= alert.target):
                        alert.triggered_at = utcnow()
                        db.commit()
                except Exception:
                    db.rollback()
                    logger.warning("alert_check_failed", extra={"event": "alert_check_failed"})
            redis.set("job:alerts:last_success", utcnow().isoformat(), ex=180)
