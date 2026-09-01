import httpx
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    server_host: str = "0.0.0.0"
    server_port: int = 8080

    request_timeout: float = Field(
        10.0, ge=0, description="Таймаут для HTTP-запросов к внешним API (в секундах)"
    )
    request_timeout_connect: float = Field(
        5.0, ge=0, description="Таймаут для установления соединения (в секундах)"
    )

    circuit_breaker_window_size: int = Field(
        10, ge=1, le=100, description="Размер окна для оценки failure rate"
    )
    circuit_breaker_failure_rate_threshold: float = Field(
        0.5, ge=0, le=1, description="Порог для открытия"
    )
    circuit_breaker_recovery_timeout: int = Field(
        60, ge=0, description="Время блокировки (в секундах)"
    )
    circuit_breaker_expected_exceptions: tuple[type[Exception], ...] = (
        httpx.RequestError,
    )

    retry_wait_time: int = Field(
        10, ge=0, description="Время ожидания между попытками retry (в секундах)"
    )
    retry_stop_attempts: int = Field(
        3, ge=0, description="Кол-во попыток для retry при ошибках HTTP-запросов"
    )
    # HTTP статусы, при которых будет срабатывать retry
    retryable_statuses: list[int] = [408, 429, 500, 502, 503, 504]
    retry_reraise: bool = True  # Переброс исключения после исчерпания попыток retry

    limiter_rate: str = "200/minute"  # Ограничение количества запросов для Rate Limiter

    use_fallback_notification: bool = (
        True  # Флаг для использования FallbackNotificationService
    )

    github_base_url: str = "https://api.github.com"
    github_token: str | None = None

    stackoverflow_base_url: str = "https://api.stackexchange.com/2.3"

    bot_base_url: str = "http://localhost:8082"

    interval_seconds: int = Field(
        15, ge=10, le=3600, description="Интервал проверки обновлений для планировщика"
    )
    batch_size_scrapper: int = Field(
        100, ge=10, le=100, description="Размер пакета для загрузки данных"
    )
    batch_size_db: int = Field(
        100, ge=10, le=100, description="Размер пакета для операций с базой данных"
    )

    notification_method: Literal["HTTP", "KAFKA"] = "KAFKA"
    kafka_bootstrap_servers: str = "localhost:9094"
    kafka_topic: str = "link.raw-updates"
    kafka_schema_registry_url: str = "http://localhost:8081"

    db_host: str = "localhost"
    db_port: int = 5434
    db_user: str
    db_password: str
    db_name: str
    access_type: Literal["SQL", "ORM"] = "ORM"

    valkey_host: str = "localhost"
    valkey_port: int = 6379
    valkey_ttl: int = Field(
        300, ge=0, le=86400, description="TTL для ключей в Valkey (в секундах)"
    )

    @property
    def database_url(self) -> str:
        """PostgreSQL URL для SQLAlchemy (asyncpg)."""
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def database_url_sync(self) -> str:
        """PostgreSQL URL для синхронных операций (Alembic)."""
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


def load_config() -> Settings:
    return Settings()
