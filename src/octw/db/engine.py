from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from octw.common.config import settings
from octw.db.tables import Base

engine = create_async_engine(settings.db_url, echo=False, pool_size=10, max_overflow=20)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def ensure_schema(db_engine: AsyncEngine | None = None) -> None:
    target = db_engine or engine
    async with target.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        dialect = conn.dialect.name
        if dialect == "postgresql":
            await conn.execute(
                text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS owner_user_id UUID")
            )
            await conn.execute(
                text(
                    "ALTER TABLE tenants "
                    "ADD COLUMN IF NOT EXISTS verification_status "
                    "VARCHAR(20) DEFAULT 'pending'"
                )
            )
            await conn.execute(
                text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS verification_error TEXT")
            )
            await conn.execute(
                text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS verified_at TIMESTAMP")
            )
            await conn.execute(
                text(
                    "UPDATE tenants SET verification_status = "
                    "COALESCE(verification_status, 'pending')"
                )
            )


async def get_session() -> AsyncSession:  # type: ignore[misc]
    async with async_session() as session:
        yield session  # type: ignore[misc]
