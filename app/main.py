import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import RequestContextMiddleware, configure_logging

configure_logging(debug=settings.DEBUG)
logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("application_startup", extra={"path": settings.ENVIRONMENT})
    yield
    logger.info("application_shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Messaging Platform API",
        description=(
            "Backend service enabling businesses to send and track messages "
            "to customers across SMS, email, and WhatsApp channels."
        ),
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
        redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    @app.get("/health", tags=["health"])
    async def health_check():
        return {"status": "ok", "environment": settings.ENVIRONMENT}

    @app.get("/health/ready", tags=["health"])
    async def readiness_check():
        """Checks downstream dependencies (DB, Redis) are reachable —
        wire this up to your k8s readinessProbe, not just `/health`."""
        from sqlalchemy import text

        from app.core.database import AsyncSessionLocal
        from app.core.security import get_redis

        checks = {"database": "unknown", "redis": "unknown"}
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as exc:  # noqa: BLE001
            checks["database"] = f"error: {exc}"

        try:
            redis = get_redis()
            await redis.ping()
            checks["redis"] = "ok"
        except Exception as exc:  # noqa: BLE001
            checks["redis"] = f"error: {exc}"

        overall_ok = all(v == "ok" for v in checks.values())
        return {"status": "ok" if overall_ok else "degraded", "checks": checks}

    return app


app = create_app()