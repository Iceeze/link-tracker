import asyncio
import json
from unittest.mock import patch
import httpx
import pytest
from testcontainers.kafka import KafkaContainer
from testcontainers.redis import DockerContainer, RedisContainer
from testcontainers.core.network import Network
from aiokafka import AIOKafkaConsumer
from confluent_kafka.serialization import SerializationContext, MessageField
from confluent_kafka.schema_registry.avro import AvroDeserializer

from src.main import process_message
from src.kafka_service import KafkaService
from src.grouping_service import GroupingService
from src.models import ProcessedUpdateMessage
from src.kafka_service import PROCESSED_UPDATE_SCHEMA


@pytest.fixture(scope="session")
def kafka_network():
    """Общая Docker-сеть для Kafka и Schema Registry."""
    with Network() as network:
        yield network


@pytest.fixture(scope="session")
def kafka_container(kafka_network):
    kafka = KafkaContainer()
    kafka.with_network(kafka_network)
    kafka.with_network_aliases("kafka")
    kafka.with_kraft()
    kafka.start()
    yield kafka
    kafka.stop()


@pytest.fixture(scope="module")
def kafka_server(kafka_container):
    return kafka_container.get_bootstrap_server()


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


@pytest.fixture(scope="module")
def redis_server():
    with RedisContainer("redis:alpine") as redis:
        yield redis


@pytest.fixture(autouse=True)
def setup_config(kafka_server, redis_server):
    from src.config import config

    config.kafka_bootstrap_servers = kafka_server
    config.kafka_group_id = "test-group"

    config.valkey_host = redis_server.get_container_host_ip()
    config.valkey_port = int(redis_server.get_exposed_port(6379))

    config.grouping_window_ms = 500
    config.summarization_threshold = 200

    config.stop_words = ["spam"]


@pytest.mark.asyncio
async def test_kafka_pipeline_valid_message(kafka_server, schema_registry_url):
    """1 часть TC-1.1 Получение события из link.raw-updates (полный цикл)."""
    input_topic = "test.raw-updates-valid"
    output_topic = "test.processed-updates-valid"

    await wait_for_schema_registry(schema_registry_url)

    kafka_service = KafkaService(
        bootstrap_servers=kafka_server,
        group_id="test-group",
        input_topic=input_topic,
        output_topic=output_topic,
        schema_registry_url=schema_registry_url,
    )

    await kafka_service.start()

    try:
        valid_message = {
            "id": 100,
            "url": "http://example.com/update/100",
            "description": "Это корректное сообщение достаточной длины без стоп-слов.",
            "author": "tester",
            "tgChatIds": [1, 2],
        }

        await kafka_service.send_message(
            input_topic, value=json.dumps(valid_message).encode("utf-8")
        )

        msg = await asyncio.wait_for(anext(kafka_service.consume()), timeout=5.0)
        raw_data = msg.value.decode("utf-8")
        data = json.loads(raw_data)

        processed_json_str = process_message(data)

        await kafka_service.stop()

        assert processed_json_str is not None
        processed_data = json.loads(processed_json_str)

        assert processed_data["id"] == 100
        assert processed_data["description"] == valid_message["description"]
        assert "priority" in processed_data
    finally:
        await kafka_service.stop()


def test_invalid_message_format():
    """1 часть TC-1.2 Некорректный формат сообщения."""
    invalid_data = '{"id": "not_an_int", "missing_fields": true}'
    result = process_message(invalid_data)
    assert result is None


@pytest.mark.asyncio
@patch("src.processor.requests.post")
async def test_kafka_pipeline_success_publication(
    mock_post, kafka_server, schema_registry_url, redis_server
):
    """2 часть TC-3.1 Успешная публикация после всех этапов обработки."""
    mock_post.side_effect = Exception("Force fallback summarization")

    input_topic = "test.raw-updates-success"
    output_topic = "test.processed-updates-success"

    await wait_for_schema_registry(schema_registry_url)

    kafka_service = KafkaService(
        bootstrap_servers=kafka_server,
        group_id="test-group-3",
        input_topic=input_topic,
        output_topic=output_topic,
        schema_registry_url=schema_registry_url,
    )
    await kafka_service.start()
    grouping_service = GroupingService(kafka_service)

    test_consumer = AIOKafkaConsumer(
        output_topic,
        bootstrap_servers=kafka_server,
        group_id="verify-group",
        auto_offset_reset="earliest",
    )
    await test_consumer.start()

    try:
        valid_message = {
            "id": 999,
            "url": "http://example.com/update/999",
            "description": "Это корректное и важное сообщение.",
            "author": "tester",
            "tgChatIds": [101],
        }

        await kafka_service.send_message(
            input_topic, value=json.dumps(valid_message).encode("utf-8")
        )

        msg = await asyncio.wait_for(anext(kafka_service.consume()), timeout=5.0)
        raw_data = msg.value.decode("utf-8")
        data = json.loads(raw_data)

        processed_json_str = process_message(data)
        assert processed_json_str is not None

        processed_msg = ProcessedUpdateMessage(**json.loads(processed_json_str))
        await grouping_service.add_message(processed_msg)

        await asyncio.sleep(0.6)

        result_msg = await asyncio.wait_for(test_consumer.getone(), timeout=5.0)

        deserializer = AvroDeserializer(
            kafka_service.schema_registry_client, schema_str=PROCESSED_UPDATE_SCHEMA
        )
        ctx = SerializationContext(output_topic, MessageField.VALUE)
        result_data = deserializer(result_msg.value, ctx)

        assert result_data["id"] == 999
        assert result_data["priority"] == "MEDIUM"
    finally:
        await test_consumer.stop()
        await grouping_service.close()
        await kafka_service.stop()


@pytest.mark.asyncio
async def test_kafka_pipeline_filtered_no_publication(
    kafka_server, schema_registry_url
):
    """2 часть TC-3.2 Отсутствие публикации при фильтрации (содержит стоп-слово)."""
    input_topic = "test.raw-updates-filtered"
    output_topic = "test.processed-updates-filtered"

    await wait_for_schema_registry(schema_registry_url)

    kafka_service = KafkaService(
        bootstrap_servers=kafka_server,
        group_id="test-group-2",
        input_topic=input_topic,
        output_topic=output_topic,
        schema_registry_url=schema_registry_url,
    )
    await kafka_service.start()

    try:
        invalid_message = {
            "id": 888,
            "url": "http://example.com/update/888",
            "description": "Это spam сообщение, должно быть отфильтровано.",
            "author": "tester",
            "tgChatIds": [101],
        }

        await kafka_service.send_message(
            input_topic, value=json.dumps(invalid_message).encode("utf-8")
        )

        msg = await asyncio.wait_for(anext(kafka_service.consume()), timeout=5.0)
        raw_data = msg.value.decode("utf-8")
        data = json.loads(raw_data)

        processed_json_str = process_message(data)

        assert processed_json_str is None
    finally:
        await kafka_service.stop()
