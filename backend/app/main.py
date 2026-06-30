from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import alerts, analytics, auth, clients, devices, fleetview, geofences, reports, scores, vehicles
from app.config import settings
from app.db import get_session
from app.security.password import hash_password


def _configure_logging() -> None:
    """Wire structlog so dev gets coloured console output and prod gets JSON."""
    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if settings.environment == "production"
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(message)s",
        force=True,
    )


_configure_logging()

_log = structlog.get_logger(__name__)


async def _seed_superadmin() -> None:
    """Create the superadmin user from env vars if they don't already exist."""
    if not settings.superadmin_email or not settings.superadmin_password:
        return
    factory = get_session()
    async with factory() as session:
        row = (
            await session.execute(
                text("SELECT * FROM auth_get_user_by_email(:e)"),
                {"e": settings.superadmin_email},
            )
        ).fetchone()
        if row is None:
            await session.execute(
                text("SELECT auth_create_superadmin(:e, :h)"),
                {"e": settings.superadmin_email, "h": hash_password(settings.superadmin_password)},
            )
            await session.commit()
            _log.info("superadmin created", email=settings.superadmin_email)
        else:
            _log.info("superadmin already exists", email=settings.superadmin_email)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await _seed_superadmin()
    _log.info("startup", environment=settings.environment)
    yield
    _log.info("shutdown")


app = FastAPI(
    title="obdmonai API",
    version="0.1.0",
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.environment == "development" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,      prefix="/auth",      tags=["auth"])
app.include_router(clients.router,   prefix="/clients",   tags=["clients"])
app.include_router(vehicles.router,  prefix="/vehicles",  tags=["vehicles"])
app.include_router(devices.router,   prefix="/devices",   tags=["devices"])
app.include_router(alerts.router,    prefix="/alerts",    tags=["alerts"])
app.include_router(geofences.router, prefix="/geofences", tags=["geofences"])
app.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
app.include_router(scores.router,    prefix="/scores",    tags=["scores"])
app.include_router(fleetview.router, prefix="/fleetview", tags=["fleetview"])
app.include_router(reports.router,   prefix="/reports",   tags=["reports"])


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
