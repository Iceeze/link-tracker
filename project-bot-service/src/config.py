import logging
import sys
from typing import Literal
import structlog
from pydantic_settings import BaseSettings, SettingsConfigDict


def configure_logging() -> None:
    """Конфигурирует логгирование."""
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Настраиваем стандартный logging, чтобы он передавал все записи в structlog
    logging.basicConfig(
        stream=sys.stdout,
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )


class Settings(BaseSettings):
    """Настройки, загружаемые из .env файла."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    bot_token: str
    bot_commands: dict[str, str] = {
        "start": "Начать работу с ботом",
        "track": "Добавить ссылку для отслеживания",
        "untrack": "Прекратить отслеживание ссылки",
        "list": "Показать список отслеживаемых ссылок",
        "help": "Показать список доступных команд",
    }

    server_host: str = "0.0.0.0"
    server_port: int = 8082

    scrapper_base_url: str = "http://localhost:8080"

    notification_method: Literal["KAFKA", "HTTP"] = "KAFKA"

    kafka_bootstrap_servers: str = "localhost:9094"
    kafka_topic: str = "link.processed-updates"
    kafka_dlq_topic: str = "link.processed-updates-dlq"
    kafka_schema_registry_url: str = "http://localhost:8081"
    kafka_max_retries: int = 3
    kafka_group_id: str = "bot-group"


config = Settings()
