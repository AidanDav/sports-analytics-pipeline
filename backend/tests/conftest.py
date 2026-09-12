import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.base import Base
from app.models import Team, Player, Game, PlayerStats, IngestionRun
from app.db.session import get_db
from app.main import app

_base_url = settings.database_url.rsplit("/", 1)[0]
TEST_DB_URL = f"{_base_url}/sports_analytics_test"


def _ensure_test_db_exists():
    async def _create():
        engine = create_async_engine(
            f"{_base_url}/postgres", isolation_level="AUTOCOMMIT"
        )
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT 1 FROM pg_database "
                    "WHERE datname = 'sports_analytics_test'"
                )
            )
            if not result.scalar():
                await conn.execute(
                    text("CREATE DATABASE sports_analytics_test")
                )
        await engine.dispose()

    asyncio.run(_create())


_ensure_test_db_exists()


@pytest.fixture()
async def db_session():
    """Each test gets its own engine, session, and clean tables.

    Creating the engine per test avoids the 'attached to a different
    loop' error that happens when asyncpg connections from one event
    loop are reused on another.
    """
    engine = create_async_engine(TEST_DB_URL, echo=False)

    # Create tables if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Truncate before each test
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())

    factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture()
async def client(db_session):
    """HTTP test client with the database dependency overridden."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()