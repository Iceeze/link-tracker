import pytest
import asyncio
from datetime import datetime, timezone
from testcontainers.kafka import KafkaContainer
from testcontainers.core.container import DockerContainer
from testcontainers.core.network import Network
from aiokafka import AIOKafkaConsumer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer, AvroSerializer
from confluent_kafka.serialization import SerializationContext, MessageField

from src.schemas import UpdateType, LinkUpdateRequest
from src.scheduler import check_updates
from src.services import KafkaNotificationService
from src.services.notification_service import LINK_UPDATE_EVENT_SCHEMA


@pytest.fixture(scope="session")
def kafka_network():
    """Общая Docker-сеть для Kafka и Schema Registry."""
    with Network() as network:
        yield network


@pytest.fixture(scope="session")
def kafka_container(kafka_network):
    """Запуск Kafka с Kraft в общей сети."""
    kafka = KafkaContainer("confluentinc/cp-kafka:7.5.0")
    kafka.with_network(kafka_network)
    kafka.with_network_aliases("kafka")
    kafka.with_kraft()
    kafka.start()
    yield kafka
    kafka.stop()


@pytest.fixture(scope="session")
def schema_registry_container(kafka_network):
    """Запуск Schema Registry в той же сети."""
    registry = (
        DockerContainer("confluentinc/cp-schema-registry:7.5.0")
        .with_network(kafka_network)
        .with_network_aliases("schema-registry")
        .with_env("SCHEMA_REGISTRY_HOST_NAME", "schema-registry")
        .with_env(
            "SCHEMA_REGISTRY_KAFKASTORE_BOOTSTRAP_SERVERS", "PLAINTEXT://kafka:9092"
        )
        .with_env("SCHEMA_REGISTRY_LISTENERS", "http://0.0.0.0:8081")
        .with_exposed_ports(8081)
    )
    registry.start()
    yield registry
    registry.stop()


@pytest.fixture(scope="session")
def schema_registry_url(schema_registry_container):
    """URL Schema Registry, доступный с хоста."""
    host = schema_registry_container.get_container_host_ip()
    port = schema_registry_container.get_exposed_port(8081)
    return f"http://{host}:{port}"


@pytest.fixture
async def kafka_resources(kafka_container, schema_registry_url):
    """
    Фикстура, которая запускает producer и consumer,
    а также возвращает function-scoped сервис уведомлений и consumer.
    """
    bootstrap_servers = kafka_container.get_bootstrap_server()
    topic = "scraper-notifications"

    notification_service = KafkaNotificationService(
        bootstrap_servers, topic, schema_registry_url
    )
    await notification_service.start()

    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers=bootstrap_servers,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        consumer_timeout_ms=10000,
    )
    await consumer.start()
    await asyncio.sleep(2)  # Дать время на инициализацию

    yield notification_service, consumer, schema_registry_url

    await consumer.stop()
    await notification_service.stop()


@pytest.mark.asyncio
async def test_scraper_to_kafka_integration(
    kafka_resources,
    mock_chat_service,
    mock_link_service,
    mock_github_scrapper,
    scheduler_mocks,
    make_link,
    make_update_details,
):
    """
    Интеграционный тест: Scraper → Kafka (Avro) → Bot.
    Проверяет полный путь от планировщика до получения Avro-сообщения.
    """
    kafka_notification_service, kafka_consumer, schema_registry_url = kafka_resources

    chat_id = 777
    url = "https://github.com/tiangolo/fastapi"

    mock_chat_service.get_all_chats.return_value = [chat_id]

    link = make_link(
        link_id=1, url=url, updated_at=datetime(2020, 1, 1, tzinfo=timezone.utc)
    )
    mock_link_service.get_links.return_value = [link]

    updates = [
        make_update_details(
            update_type=UpdateType.GITHUB_PR,
            title="Awesome PR",
            username="dev_user",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            preview="This PR adds great features",
            url=f"{url}/pull/123",
        )
    ]
    mock_github_scrapper.check_for_updates.return_value = updates

    with scheduler_mocks():
        await check_updates(
            chat_service=mock_chat_service,
            link_service=mock_link_service,
            notification_service=kafka_notification_service,
        )

    raw_message = await asyncio.wait_for(kafka_consumer.getone(), timeout=10.0)
    assert raw_message.value is not None, "Сообщение не было отправлено в Kafka"

    # Десериализация Avro
    sr_client = SchemaRegistryClient({"url": schema_registry_url})
    deserializer = AvroDeserializer(schema_registry_client=sr_client)
    ctx = SerializationContext("scraper-notifications", MessageField.VALUE)
    data = deserializer(raw_message.value, ctx)

    request = LinkUpdateRequest.model_validate(data)

    assert request.id == link.id
    assert request.url == url
    assert request.tgChatIds == [chat_id]
    assert "Awesome PR" in request.description
    assert "dev_user" in request.description
    assert "https://github.com/tiangolo/fastapi/pull/123" in request.description

    mock_link_service.update_link_updated_at.assert_awaited_once()
    call_args = mock_link_service.update_link_updated_at.await_args
    assert call_args[0][0] == chat_id
    assert call_args[0][1] == url
    updated_at = call_args[0][2]
    assert updated_at is not None


@pytest.mark.asyncio
async def test_avro_serialization(schema_registry_url):
    """
    Тест корректности Avro-сериализации/десериализации.
    """
    topic = "test-topic"
    original = LinkUpdateRequest(
        id=42,
        url="https://example.com",
        description="Test description",
        tgChatIds=[100, 200],
    )

    sr_client = SchemaRegistryClient({"url": schema_registry_url})
    serializer = AvroSerializer(
        schema_registry_client=sr_client, schema_str=LINK_UPDATE_EVENT_SCHEMA
    )
    deserializer = AvroDeserializer(schema_registry_client=sr_client)

    ctx = SerializationContext(topic, MessageField.VALUE)

    serialized = serializer(original.model_dump(mode="json"), ctx)
    deserialized_data = deserializer(serialized, ctx)
    restored = LinkUpdateRequest.model_validate(deserialized_data)

    assert restored == original
