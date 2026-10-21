import logging
import time
from contextlib import asynccontextmanager
from decimal import getcontext

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.logging_config import setup_logging
from app.db import SessionLocal
from app.routers import api, auth, broker
from app.middleware import UploadLimitMiddleware
from app.services.cache import metric, redis

getcontext().prec = 120
settings = get_settings()


setup_logging()
logger = logging.getLogger("grow_hike")


@asynccontextmanager
async def lifespan(app):
    settings.validate_production()
    yield


app = FastAPI(title="GROW HIKE API", version="1.0.0", lifespan=lifespan, description="Decimal-safe paper trading and read-only portfolio tracking. No real brokerage orders.")
app.add_middleware(UploadLimitMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_url], allow_credentials=True, allow_methods=["GET", "POST", "DELETE"], allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "Idempotency-Key"])


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Avoid echoing passwords, tokens or uploaded contents in error bodies.
    return JSONResponse(status_code=422, content={"detail": [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]})


@app.exception_handler(RedisError)
async def redis_error(request, exc):
    return JSONResponse(status_code=503, content={"detail": "Cache temporarily unavailable"})


@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    logger.error("database_unavailable")
    return JSONResponse(status_code=503, content={"detail": "Database temporarily unavailable"})


@app.middleware("http")
async def observe(request, call_next):
    if request.url.path in ("/health", "/ready"):
        return await call_next(request)
    start = time.perf_counter_ns()
    response = await call_next(request)
    elapsed_us = (time.perf_counter_ns() - start) // 1000
    def record_metrics():
        metric("http_requests")
        metric(f"http_status:{response.status_code}")
        try:
            if request.url.path != "/api/stream":
                with redis.pipeline() as p:
                    p.lpush("request_times_us", elapsed_us)
                    p.ltrim("request_times_us", 0, 999)
                    p.execute()
        except RedisError:
            pass
    await run_in_threadpool(record_metrics)
    # Query strings and headers are deliberately omitted, including OAuth callback codes.
    logger.info({"name": "http_request", "method": request.method, "status": response.status_code, "elapsed_us": elapsed_us})
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.get("/health", tags=["Operations"])
def health():
    return {"status": "ok"}


@app.get("/ready", tags=["Operations"])
def ready():
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1 FROM alembic_version LIMIT 1"))
        redis.ping()
        return {"status": "ready", "database": "ok", "cache": "ok"}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "not_ready"})


app.include_router(auth.router, prefix="/api")
app.include_router(api.router, prefix="/api")
app.include_router(broker.router, prefix="/api")
