"""
AegisCX Database Module
=========================
Agnostic SQLAlchemy setup for PostgreSQL or SQLite.
Provides:
  - Async engine and session factory with automatic fallback
  - Base declarative class for all models
  - get_db dependency for FastAPI route injection
  - Health check & bootstrap utilities

All queries throughout the app use async sessions for non-blocking I/O.
"""

import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

# ─── Connection Logic ───────────────────────────────────────────────────────────
DATABASE_URL = settings.database_url

# Automatic fallback to SQLite if PostgreSQL is unreachable or not configured
if not DATABASE_URL or "postgresql" not in DATABASE_URL:
    # Ensure data directory exists for sqlite
    os.makedirs("./data", exist_ok=True)
    DATABASE_URL = "sqlite+aiosqlite:///./data/aegiscx.db"
    
is_sqlite = DATABASE_URL.startswith("sqlite")

# ─── Async Engine ──────────────────────────────────────────────────────────────
# Configure engine based on driver type
engine_args = {
    "echo": settings.debug,
}

if not is_sqlite:
    # PostgreSQL specific optimizations
    engine_args.update({
        "pool_size": 20,
        "max_overflow": 40,
        "pool_pre_ping": True,
        "pool_recycle": 3600,
    })
else:
    # SQLite specific - ensure we don't have multiple writers on a single-file DB
    # aiosqlite handles the async aspect
    pass

engine = create_async_engine(DATABASE_URL, **engine_args)

# ─── Session Factory ────────────────────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# ─── Declarative Base ───────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy ORM models.
    Provides metadata and declarative mapping.
    """
    pass


# ─── FastAPI Dependency ─────────────────────────────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides an async database session.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ─── Bootstrap Utilities ────────────────────────────────────────────────────────
async def init_db() -> None:
    """
    Initialize the database tables. 
    In development, this bootstraps the schema from metadata.
    """
    async with engine.begin() as conn:
        # Import models inside to ensure they are registered with Base.metadata
        from app.models.models import Base as ModelBase
        await conn.run_sync(ModelBase.metadata.create_all)

    await _seed_development_session()


async def check_db_health() -> bool:
    """
    Ping the database to verify connectivity.
    """
    from sqlalchemy import text
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def _seed_development_session() -> None:
    """
    Create a deterministic local admin identity in development so the app can
    operate end-to-end without forcing a manual signup flow first.
    """
    if settings.environment != "development":
        return

    from app.core.security import hash_password
    from app.models.models import Company, User

    company_id = "00000000-0000-0000-0000-000000000000"
    user_id = "00000000-0000-0000-0000-000000000000"

    async with AsyncSessionLocal() as session:
        company = await session.get(Company, company_id)
        if company is None:
            company = Company(
                id=company_id,
                name="AegisCX Local Workspace",
                industry="customer intelligence",
                subscription_tier="enterprise",
                is_active=True,
            )
            session.add(company)

        user = await session.get(User, user_id)
        if user is None:
            user = User(
                id=user_id,
                email="demo@aegiscx.app",
                name="Local Demo Admin",
                password_hash=hash_password("AegisCX123"),
                role="admin",
                company_id=company_id,
                is_active=True,
            )
            session.add(user)
        else:
            user.email = "demo@aegiscx.app"
            user.name = "Local Demo Admin"
            # Keep the deterministic demo password healthy across local restarts.
            user.password_hash = hash_password("AegisCX123")
            user.company_id = company_id
            user.role = "admin"
            user.is_active = True

        await session.commit()
