import pytest
from unittest.mock import MagicMock, patch

from src.services import (
    get_notification_service,
    KafkaNotificationService,
    HTTPNotificationService,
    FallbackNotificationService,
)


@pytest.fixture
def mock_config():
    """Фикстура для имитации объекта конфигурации (Settings)."""
    config = MagicMock()
    config.bot_base_url = "http://example.com/bot/"
    config.kafka_bootstrap_servers = "localhost:9092"
    config.kafka_topic = "test-topic"
    config.kafka_schema_registry_url = "http://localhost:8081"
    config.use_fallback_notification = False

    return config


@patch("src.services.notification_service.AIOKafkaProducer")
@patch("src.services.notification_service.AvroSerializer")
@patch("src.services.notification_service.SchemaRegistryClient")
def test_get_notification_service_returns_kafka(
    mock_schema_registry, mock_avro_serializer, mock_kafka_producer, mock_config
):
    """
    Тест проверяет, что при method == 'KAFKA' фабрика возвращает KafkaNotificationService
    с правильными параметрами.
    """
    mock_config.notification_method = "KAFKA"

    service = get_notification_service(mock_config)

    assert isinstance(service, KafkaNotificationService)
    assert service.bootstrap_servers == mock_config.kafka_bootstrap_servers
    assert service.topic == mock_config.kafka_topic

    mock_schema_registry.assert_called_once_with(
        {"url": mock_config.kafka_schema_registry_url}
    )
    mock_kafka_producer.assert_called_once_with(
        bootstrap_servers=mock_config.kafka_bootstrap_servers
    )
    mock_avro_serializer.assert_called_once()


def test_get_notification_service_returns_http(mock_config):
    """
    Тест проверяет, что при method != 'KAFKA' фабрика возвращает HTTPNotificationService.
    """
    mock_config.notification_method = "HTTP"

    service = get_notification_service(mock_config)

    assert isinstance(service, HTTPNotificationService)
    assert service.base_url == "http://example.com/bot"


def test_get_notification_service_default_fallback(mock_config):
    """
    Тест проверяет, что при любом неизвестном методе фоллбэком выступает HTTP реализация.
    """
    mock_config.notification_method = "UNKNOWN_METHOD"

    service = get_notification_service(mock_config)

    assert isinstance(service, HTTPNotificationService)


@patch("src.services.notification_service.AIOKafkaProducer")
@patch("src.services.notification_service.AvroSerializer")
@patch("src.services.notification_service.SchemaRegistryClient")
def test_get_notification_service_with_fallback(
    mock_schema_registry, mock_avro_serializer, mock_kafka_producer, mock_config
):
    """
    Тест проверяет, что при включенном флагу use_fallback_notification фабрика возвращает
    FallbackNotificationService, который использует Kafka в качестве primary и HTTP в качестве secondary.
    """
    mock_config.notification_method = "KAFKA"
    mock_config.use_fallback_notification = True

    service = get_notification_service(mock_config)

    assert isinstance(service, FallbackNotificationService)
