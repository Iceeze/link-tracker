import httpx
import pytest
import asyncio
import contextlib
import uuid
from unittest.mock import AsyncMock, patch
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from testcontainers.kafka import KafkaContainer
from testcontainers.core.container import DockerContainer
from testcontainers.core.network import Network
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer, AvroDeserializer
from confluent_kafka.serialization import SerializationContext, MessageField

from src.kafka import Consumer
from src.kafka.consumer import PROCESSED_UPDATE_SCHEMA
from src.schemas import PriorityEnum


@pytest.fixture(scope="session")
def kafka_network():
    """Общая сеть для Kafka и Schema Registry."""
    with Network() as net:
        yield net


@pytest.fixture(scope="session")
def kafka_container(kafka_network):
    kafka = KafkaContainer()
    kafka.with_network(kafka_network)
    kafka.with_network_aliases("kafka")
    kafka.with_kraft()
    kafka.start()
    yield kafka
    kafka.stop()


@pytest.fixture(scope="session")
def schema_registry_container(kafka_network):
    registry = (
        DockerContainer("confluentinc/cp-schema-registry:7.5.0")
        .with_network(kafka_network)
        .with_network_aliases("schema-registry")
        .with_env("SCHEMA_REGISTRY_HOST_NAME", "schema-registry")
        .with_env(
            "SCHEMA_REGISTRY_KAFKASTORE_BOOTSTRAP_SERVERS",
            "PLAINTEXT://kafka:9092",
        )
        .with_env("SCHEMA_REGISTRY_LISTENERS", "http://0.0.0.0:8081")
        .with_exposed_ports(8081)
    )
    registry.start()
    yield registry
    registry.stop()


@pytest.fixture(scope="session")
def schema_registry_url(schema_registry_container):
    host = schema_registry_container.get_container_host_ip()
    port = schema_registry_container.get_exposed_port(8081)
    return f"http://{host}:{port}"


async def wait_for_schema_registry(url: str, timeout: float = 30.0):
    """Ждёт, пока Schema Registry станет доступен."""
    deadline = asyncio.get_event_loop().time() + timeout
    async with httpx.AsyncClient() as client:
        while True:
            try:
                resp = await client.get(f"{url}/subjects", timeout=2.0)
                if resp.status_code == 200:
                    return
            except httpx.TransportError:
                pass
            if asyncio.get_event_loop().time() > deadline:
                raise TimeoutError("Schema Registry не поднялся за отведённое время")
            await asyncio.sleep(0.5)


async def create_topics(bootstrap_servers: str, topics: list[str]):
    """Создаёт топики, если их нет."""
    admin = AIOKafkaAdminClient(bootstrap_servers=bootstrap_servers)
    await admin.start()
    try:
        existing = await admin.list_topics()
        to_create = [
            NewTopic(name=t, num_partitions=1, replication_factor=1)
            for t in topics
            if t not in existing
        ]
        if to_create:
            await admin.create_topics(to_create)
    finally:
        await admin.close()


@pytest.fixture
def kafka_topics():
    """Генерирует уникальные топики для каждого теста для изоляции."""
    uid = uuid.uuid4().hex
    return f"topic-{uid}", f"dlq-{uid}"


@pytest.fixture
async def kafka_resources(kafka_container, kafka_topics, schema_registry_url):
    topic, dlq_topic = kafka_topics
    bootstrap_servers = kafka_container.get_bootstrap_server()

    await wait_for_schema_registry(schema_registry_url)
    await create_topics(bootstrap_servers, [topic, dlq_topic])

    producer = AIOKafkaProducer(bootstrap_servers=bootstrap_servers)
    await producer.start()

    app_consumer = Consumer(
        bootstrap_servers=bootstrap_servers,
        topic=topic,
        dlq_topic=dlq_topic,
        schema_registry_url=schema_registry_url,
        group_id="bot-test-group",
        max_retries=3,
    )
    await app_consumer.start()

    dlq_consumer = AIOKafkaConsumer(
        dlq_topic,
        bootstrap_servers=bootstrap_servers,
        group_id=f"test-dlq-{uuid.uuid4().hex}",
        auto_offset_reset="earliest",
    )
    await dlq_consumer.start()

    await asyncio.sleep(2)

    yield producer, app_consumer, dlq_consumer, topic, dlq_topic, schema_registry_url

    await dlq_consumer.stop()
    await app_consumer.stop()
    await producer.stop()


@pytest.fixture
async def bot_mock():
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    return bot


async def get_single_message(consumer: AIOKafkaConsumer, timeout: float = 10.0):
    """Получает одно сообщение из consumer'а с таймаутом."""
    return await asyncio.wait_for(consumer.getone(), timeout=timeout)


def avro_serialize(payload: dict, schema_registry_url: str, topic: str) -> bytes:
    """Сериализует dict в Avro, используя Schema Registry."""
    client = SchemaRegistryClient({"url": schema_registry_url})
    serializer = AvroSerializer(
        schema_registry_client=client,
        schema_str=PROCESSED_UPDATE_SCHEMA,
    )
    ctx = SerializationContext(topic, MessageField.VALUE)
    return serializer(payload, ctx)


def avro_deserialize(raw_bytes: bytes, schema_registry_url: str) -> dict:
    """Десериализует Avro обратно в dict."""
    client = SchemaRegistryClient({"url": schema_registry_url})
    deserializer = AvroDeserializer(schema_registry_client=client)
    ctx = SerializationContext("dummy", MessageField.VALUE)
    return deserializer(raw_bytes, ctx)


@pytest.mark.asyncio
async def test_valid_message_is_processed_successfully(kafka_resources, bot_mock):
    """Отправка валидного сообщения → успешная обработка."""
    producer, app_consumer, _, topic, _, sr_url = kafka_resources

    processed = asyncio.Event()
    captured = {}

    async def fake_process_notification(update, bot):
        captured["update"] = update
        processed.set()

    with patch(
        "src.kafka.consumer.process_notification",
        side_effect=fake_process_notification,
    ):
        task = asyncio.create_task(app_consumer.consume(bot_mock))

        payload = {
            "id": 1,
            "tgChatIds": [777],
            "description": "Awesome PR",
            "priority": PriorityEnum.HIGH.value,
            "url": "https://example.com",
        }

        avro_bytes = avro_serialize(payload, sr_url, topic)
        await producer.send_and_wait(topic, avro_bytes)

        await asyncio.wait_for(processed.wait(), timeout=10)

        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    assert captured["update"].id == 1
    assert captured["update"].tgChatIds == [777]


@pytest.mark.asyncio
async def test_invalid_avro_goes_to_dlq(kafka_resources, bot_mock):
    """Не Avro данные (сырые байты) → ошибка десериализации → DLQ."""
    producer, app_consumer, dlq_consumer, topic, _, _ = kafka_resources

    task = asyncio.create_task(app_consumer.consume(bot_mock))

    bad_payload = b"this is not avro"
    await producer.send_and_wait(topic, bad_payload)

    dlq_msg = await asyncio.wait_for(get_single_message(dlq_consumer), timeout=10)

    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert dlq_msg.value == bad_payload
    headers = dict(dlq_msg.headers)
    assert headers["error_reason"].startswith(b"deserialization_error")


@pytest.mark.asyncio
async def test_processing_error_retries_and_succeeds(kafka_resources, bot_mock):
    """Ошибка при обработке → ретраи → успешная обработка."""
    producer, app_consumer, _, topic, _, sr_url = kafka_resources

    processed = asyncio.Event()
    call_count = 0

    async def fake_process_with_fails(update, bot):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("Временная ошибка API")
        processed.set()

    with patch(
        "src.kafka.consumer.process_notification",
        side_effect=fake_process_with_fails,
    ):
        task = asyncio.create_task(app_consumer.consume(bot_mock))

        payload = {
            "id": 1,
            "url": "https://example.com",
            "tgChatIds": [123],
            "description": "test",
            "priority": PriorityEnum.MEDIUM.value,
        }
        avro_bytes = avro_serialize(payload, sr_url, topic)
        await producer.send_and_wait(topic, avro_bytes)

        await asyncio.wait_for(processed.wait(), timeout=10)

        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    assert call_count == 3


@pytest.mark.asyncio
async def test_processing_error_exhausts_retries_and_goes_to_dlq(
    kafka_resources, bot_mock
):
    """Постоянная ошибка при обработке → исчерпание попыток → DLQ."""
    producer, app_consumer, dlq_consumer, topic, _, sr_url = kafka_resources

    call_count = 0

    async def always_failing_process(update, bot):
        nonlocal call_count
        call_count += 1
        raise RuntimeError("Критическая ошибка")

    with patch(
        "src.kafka.consumer.process_notification",
        side_effect=always_failing_process,
    ):
        task = asyncio.create_task(app_consumer.consume(bot_mock))

        payload = {
            "id": 1,
            "url": "https://example.com",
            "tgChatIds": [123],
            "description": "test",
            "priority": PriorityEnum.MEDIUM.value,
        }
        avro_bytes = avro_serialize(payload, sr_url, topic)
        await producer.send_and_wait(topic, avro_bytes)

        dlq_msg = await asyncio.wait_for(get_single_message(dlq_consumer), timeout=15)

        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    assert call_count == app_consumer.max_retries
    assert dlq_msg.value == avro_bytes
    headers = dict(dlq_msg.headers)
    assert headers["error_reason"].startswith(b"processing_error")
