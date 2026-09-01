from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    request_timeout: int = Field(
        15, description="Макс. время ожидания ответа от AI API в секундах"
    )

    # AI API
    ai_api_url: str = "https://router.huggingface.co/v1/chat/completions"
    hf_api_token: str = ""

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9094"
    kafka_group_id: str = "ai-agent-group"
    kafka_input_topic: str = "link.raw-updates"
    kafka_output_topic: str = "link.processed-updates"
    kafka_schema_registry_url: str = "http://localhost:8081"

    # Filtering
    stop_words: list[str] = ["spam", "ads", "scam"]
    excluded_authors: list[str] = ["bot-user"]
    filter_min_length: int = 20

    # Summarization
    summarization_threshold: int = 500

    # Prioritization
    high_keywords: list[str] = ["critical", "urgent", "breaking", "security"]
    low_keywords: list[str] = ["minor", "typo", "chore", "docs"]

    # Grouping
    grouping_window_ms: int = 60000

    # Valkey
    valkey_host: str = "localhost"
    valkey_port: int = 6379


config = Settings()
