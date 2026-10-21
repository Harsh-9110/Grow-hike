from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_engine(get_settings().database_url, hide_parameters=True, pool_pre_ping=True, pool_size=10, max_overflow=10)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_db():
    with SessionLocal() as db:
        yield db


@lru_cache(maxsize=4)
def cache_engine_for(url):
    # A separate small pool keeps cache writes from waiting on all the request readers.
    return create_engine(url, hide_parameters=True, pool_pre_ping=True, pool_size=2, max_overflow=2)
