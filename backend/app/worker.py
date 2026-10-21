from apscheduler.schedulers.blocking import BlockingScheduler

from app.services.jobs import alerts_job, snapshot_job
from app.config import get_settings
from app.logging_config import setup_logging

setup_logging()
get_settings().validate_production()
scheduler = BlockingScheduler(timezone="Asia/Kolkata")
scheduler.add_job(snapshot_job, "cron", day_of_week="mon-fri", hour=23, minute=45, id="daily_snapshot", max_instances=1, coalesce=True, misfire_grace_time=3600)
scheduler.add_job(alerts_job, "interval", seconds=60, id="alerts", max_instances=1, coalesce=True)
if __name__ == "__main__":
    snapshot_job()
    alerts_job()
    scheduler.start()
