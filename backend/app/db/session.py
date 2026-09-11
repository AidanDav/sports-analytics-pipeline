from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
# Creates a connection to the database using the settings from the config file. The connection is created using the 
# asyncpg driver for PostgreSQL. The echo parameter is set to True if the app is in development mode, which will 
# log all SQL statements to the console. The pool_pre_ping parameter is set to True to ensure that connections are 
# still valid before using them.
engine = create_async_engine(
    settings.database_url,
    echo=settings.app_env == "development",
    pool_pre_ping=True,
)
# A factory for creating new asynchronous database sessions. The class_ parameter specifies 
# that the sessions will be instances of AsyncSession, and the expire_on_commit parameter 
# is set to False to prevent SQLAlchemy from expiring objects after a commit.
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# This is a FastAPI dependency that yields an async database session. It uses the async_session factory to create 
# a new session, and it commits the session if there are no exceptions. If an exception occurs, it rolls back the 
# session and raises the exception.
async def get_db() -> AsyncSession:
    """FastAPI dependency that yields an async database session."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise