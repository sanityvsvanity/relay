"""Database connection pool and schema initialization."""

from __future__ import annotations

from pathlib import Path

from psycopg_pool import AsyncConnectionPool

from app.config import settings

_pool: AsyncConnectionPool | None = None
_schema_path = Path(__file__).parent / "schema.sql"


async def get_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        conninfo = settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")
        _pool = AsyncConnectionPool(conninfo=conninfo, min_size=1, max_size=5, open=False)
        await _pool.open()
        if _schema_path.exists():
            async with _pool.connection() as conn:
                await conn.execute(_schema_path.read_text())
                await conn.commit()
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
