"""Async SQLAlchemy setup: engine, session factory, declarative base.

The schema itself is owned by db/schema.sql — the ORM models mirror it,
they do not create it.
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    get_settings().database_url,
    pool_size=5,           # keep small: max_connections=30 on the B1s Postgres
    max_overflow=5,
    pool_pre_ping=True,
)

SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: one session per request, always closed."""
    async with SessionFactory() as session:
        yield session
