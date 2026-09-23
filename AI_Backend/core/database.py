"""
The AI backend's one database connection
=========================================
The Node backend owns the database: every table, every migration, every
write about farms, readings and conversations. This service is stateless
compute and never touches those.

The single exception is the knowledge index (`knowledge_chunks`), which the
retrieval agent searches on every knowledge question. Routing that through
Node would add a network hop to the hottest RAG path for nothing, so this
module opens a small pool used only for it - and for the admin reindex that
rebuilds it from the OKF bundle.

Lazy: importing the AI backend never requires a database. With no
DATABASE_URL, retrieval falls back to the curated OKF layer alone.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger("farmxpert.ai.db")

_engine: Optional[AsyncEngine] = None


def database_url() -> Optional[str]:
    url = os.getenv("DATABASE_URL") or None
    if not url:
        return None
    # A URL copied from a dashboard names the sync driver; this service is async.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix):]
    return url


def configured() -> bool:
    return database_url() is not None


def engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        url = database_url()
        if url is None:
            raise RuntimeError("DATABASE_URL is not set; the knowledge index is unavailable.")
        _engine = create_async_engine(
            url,
            # Small on purpose: this pool serves one query shape. The Node
            # backend holds the connections that do the real work.
            pool_size=int(os.getenv("AI_DB_POOL_SIZE", "3")),
            max_overflow=2,
            pool_pre_ping=True,          # managed Postgres drops idle connections
            pool_recycle=1800,
            connect_args={"server_settings": {"application_name": "farmxpert-ai",
                                              "statement_timeout": "5000"},
                          "statement_cache_size": 0})
    return _engine


def session() -> AsyncSession:
    return async_sessionmaker(bind=engine(), class_=AsyncSession,
                              expire_on_commit=False)()


async def dispose() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
