"""
CFIS FastAPI Application
========================
Customer Feedback Intelligence System main application entry point.
"""

import time
from contextlib import asynccontextmanager
from threading import Thread
from typing import Any

import structlog
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.routes import admin, analytics, auth, recordings, reports
from app.core.config import get_settings
from app.core.database import DATABASE_URL, check_db_health, engine, init_db

settings = get_settings()

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.CallsiteParameterAdder(
            [structlog.processors.CallsiteParameter.MODULE],
        ),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.ExceptionRenderer(),
        structlog.dev.ConsoleRenderer(colors=False),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)
log = structlog.get_logger("aegiscx.main")

limiter = Limiter(key_func=get_remote_address)


def _warm_model_runtime() -> None:
    """
    Preload the shared STT and NLP caches after the API starts serving so the
    first real upload does not pay the full model boot penalty.
    """
    try:
        from app.services.stt.engine import STTEngine

        STTEngine.warmup()
        log.info("aegiscx_stt_warmup_ready")
    except Exception as exc:
        log.warning("aegiscx_stt_warmup_skipped", error=str(exc))

    try:
        from app.services.nlp.pipeline import IntelligencePipeline

        IntelligencePipeline.warmup()
        log.info("aegiscx_nlp_warmup_ready")
    except Exception as exc:
        log.warning("aegiscx_nlp_warmup_skipped", error=str(exc))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle manager.
    On startup: bootstrap DB, validate connectivity, and trigger warmup.
    On shutdown: dispose the DB engine cleanly.
    """
    log.info("aegiscx_startup", version=settings.app_version, env=settings.environment)
    log.info("aegiscx_db_init_start", target=DATABASE_URL)

    try:
        await init_db()
        log.info("aegiscx_db_init_success")
    except Exception as exc:
        log.error("aegiscx_db_init_failed", error=str(exc))

    db_ok = await check_db_health()
    if not db_ok:
        log.error("aegiscx_startup_failed", reason="database_unreachable")
        if "sqlite" not in DATABASE_URL:
            raise RuntimeError(
                f"Cannot connect to database ({DATABASE_URL}) - ensure the service is running."
            )

    Thread(target=_warm_model_runtime, daemon=True).start()
    log.info("aegiscx_ready", message="All systems operational")
    yield

    await engine.dispose()
    log.info("aegiscx_shutdown", message="Engine disposed cleanly")


app = FastAPI(
    title="Customer Feedback Intelligence System (CFIS) API",
    description=(
        "Enterprise customer feedback intelligence system. "
        "Transforms audio and video feedback into deep behavioral intelligence."
    ),
    version=settings.app_version,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    GZipMiddleware,
    minimum_size=500,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every incoming request with method, path, status, and duration."""
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    log.info(
        "http_request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=duration_ms,
        client=request.client.host if request.client else "unknown",
    )
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all exception handler for unexpected server errors."""
    log.error(
        "unhandled_exception",
        path=request.url.path,
        error=str(exc),
        error_type=type(exc).__name__,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred. Please try again.",
            "request_id": request.headers.get("X-Request-ID"),
        },
    )


API_PREFIX = "/api/v1"

app.include_router(auth.router, prefix=f"{API_PREFIX}/auth", tags=["Authentication"])
app.include_router(recordings.router, prefix=f"{API_PREFIX}/recordings", tags=["Recordings"])
app.include_router(analytics.router, prefix=f"{API_PREFIX}/analytics", tags=["Analytics"])
app.include_router(reports.router, prefix=f"{API_PREFIX}/reports", tags=["Reports"])
app.include_router(admin.router, prefix=f"{API_PREFIX}/admin", tags=["Admin"])


@app.get("/api/v1/health", tags=["Health"])
@limiter.limit("60/minute")
async def health_check(request: Request) -> dict[str, Any]:
    """
    System health endpoint.
    """
    db_healthy = await check_db_health()
    return {
        "status": "healthy" if db_healthy else "degraded",
        "version": settings.app_version,
        "environment": settings.environment,
        "database_type": "sqlite" if "sqlite" in DATABASE_URL else "postgresql",
        "components": {
            "api": "healthy",
            "database": "healthy" if db_healthy else "unreachable",
        },
    }


@app.get("/", include_in_schema=False)
async def root():
    return {"message": "AegisCX API - visit /api/docs for documentation"}
