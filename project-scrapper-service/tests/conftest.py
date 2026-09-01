import os

os.environ["REQUEST_TIMEOUT"] = "0.5"
os.environ["REQUEST_TIMEOUT_CONNECT"] = "0.5"
os.environ["RETRY_WAIT_TIME"] = "1"
os.environ["RETRY_STOP_ATTEMPTS"] = "3"
os.environ["CIRCUIT_BREAKER_WINDOW_SIZE"] = "3"
os.environ["CIRCUIT_BREAKER_FAILURE_RATE_THRESHOLD"] = "0.5"
os.environ["CIRCUIT_BREAKER_RECOVERY_TIMEOUT"] = "1"

import pytest
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text, create_engine
from urllib.parse import urlparse
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from src.api.app import create_app
from src.config import Settings
from src.clients import ValkeyClient
from src.database import run_migrations
from src.schemas import (
    LinkResponse,
    LinkUpdateDetails,
    UpdateType,
)

BATCH_SIZE_DB = 100


@pytest.fixture(scope="session")
def postgres_container():
    postgres = PostgresContainer("postgres:16-alpine", driver="psycopg2")
    postgres.start()
    yield postgres
    postgres.stop()


@pytest.fixture(scope="session")
def redis_container():
    redis = RedisContainer("redis:7-alpine")
    redis.start()
    yield redis
    redis.stop()


def _get_test_config(
    container, access_type: str, valkey_host: str, valkey_port: int
) -> Settings:
    connection_url = container.get_connection_url()
    parsed = urlparse(connection_url.replace("postgresql+psycopg2://", "postgresql://"))
    return Settings.model_validate(
        {
            "db_host": parsed.hostname,
            "db_port": parsed.port,
            "db_name": parsed.path.lstrip("/"),
            "db_user": parsed.username,
            "db_password": parsed.password,
            "access_type": access_type,
            "valkey_host": valkey_host,
            "valkey_port": valkey_port,
            "valkey_ttl": 60,
        }
    )


@pytest.fixture(scope="session")
def test_config_orm(postgres_container, redis_container) -> Settings:
    return _get_test_config(
        postgres_container,
        "ORM",
        redis_container.get_container_host_ip(),
        redis_container.get_exposed_port(6379),
    )


@pytest.fixture(scope="session")
def test_config_sql(postgres_container, redis_container) -> Settings:
    return _get_test_config(
        postgres_container,
        "SQL",
        redis_container.get_container_host_ip(),
        redis_container.get_exposed_port(6379),
    )


@pytest.fixture(scope="session", autouse=True)
def setup_database(test_config_orm: Settings):
    run_migrations(test_config_orm)


@pytest.fixture(scope="function")
def clean_db(test_config_orm: Settings):
    sync_engine = create_engine(test_config_orm.database_url_sync)
    try:
        with sync_engine.connect() as conn:
            conn.execute(text("DELETE FROM link_tag"))
            conn.execute(text("DELETE FROM link_chat"))
            conn.execute(text("DELETE FROM links"))
            conn.execute(text("DELETE FROM chats"))
            conn.commit()
        yield
    finally:
        sync_engine.dispose()


@pytest.fixture
async def valkey_client(test_config_orm: Settings):

    client = ValkeyClient(
        host=test_config_orm.valkey_host,
        port=test_config_orm.valkey_port,
        ttl=test_config_orm.valkey_ttl,
    )
    yield client
    await client.aclose()


@pytest.fixture
async def clean_cache(valkey_client):
    cursor = 0
    while True:
        cursor, keys = await valkey_client.client.scan(
            cursor, match="chat_links:*", count=100
        )
        if keys:
            await valkey_client.client.delete(*keys)
        if cursor == 0:
            break
    yield


async def _create_client(config: Settings):
    app = create_app(config, skip_migrations=False, use_scheduler=False)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client


@pytest.fixture(params=["ORM", "SQL"])
async def client(request, test_config_orm, test_config_sql, clean_db):
    access_type = request.param
    config = test_config_orm if access_type == "ORM" else test_config_sql
    async for client in _create_client(config):
        yield client


@pytest.fixture
def mock_chat_service() -> AsyncMock:
    service = AsyncMock()
    service.get_all_chats.return_value = []
    return service


@pytest.fixture
def mock_link_service() -> AsyncMock:
    service = AsyncMock()
    service.get_links.return_value = []
    return service


@pytest.fixture
def mock_notification_service() -> AsyncMock:
    service = AsyncMock()
    service.send_update = AsyncMock(return_value=True)
    return service


@pytest.fixture
def mock_github_scrapper() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_stackoverflow_scrapper() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def scheduler_mocks(
    mock_github_scrapper: AsyncMock,
    mock_stackoverflow_scrapper: AsyncMock,
):
    """Контекстный менеджер, патчащий все зависимости scheduler."""

    @contextmanager
    def _patch_scheduler():
        with patch("src.scheduler.github_scrapper", mock_github_scrapper), patch(
            "src.scheduler.stackoverflow_scrapper", mock_stackoverflow_scrapper
        ), patch("src.scheduler.config", batch_size_db=BATCH_SIZE_DB):
            yield

    return _patch_scheduler


@pytest.fixture
def make_link():
    def _make(
        link_id: int = 1,
        url: str = "https://github.com/tiangolo/fastapi",
        tags: list[str] | None = None,
        filters: list[str] | None = None,
        updated_at: datetime | None = None,
    ) -> LinkResponse:
        return LinkResponse(
            id=link_id,
            url=url,
            tags=tags or [],
            filters=filters or [],
            updated_at=updated_at,
        )

    return _make


@pytest.fixture
def make_update_details():
    def _make(
        update_type: UpdateType = UpdateType.GITHUB_PR,
        title: str = "Update",
        username: str = "user",
        created_at: datetime | None = None,
        preview: str = "Preview",
        url: str = "https://example.com/update",
    ) -> LinkUpdateDetails:
        return LinkUpdateDetails(
            update_type=update_type,
            title=title,
            username=username,
            created_at=created_at or datetime(2024, 1, 1, tzinfo=timezone.utc),
            preview=preview,
            url=url,
        )

    return _make
