from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)
import asyncpg

from src.config import Settings


def get_db_engine(config: Settings) -> AsyncEngine:
    """Создание асинхронного engine для SQLAlchemy."""
    return create_async_engine(
        url=config.database_url,
        echo=False,
        pool_pre_ping=True,
    )


def get_db_session(engine) -> async_sessionmaker[AsyncSession]:
    """Создание фабрики сессий."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def get_asyncpg_pool(config: Settings) -> asyncpg.Pool:
    """Создание пула подключений asyncpg для raw SQL."""
    return await asyncpg.create_pool(
        host=config.db_host,
        port=config.db_port,
        database=config.db_name,
        user=config.db_user,
        password=config.db_password,
        min_size=5,
        max_size=20,
    )
