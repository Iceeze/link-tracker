import asyncio
import json

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock
from fakeredis.aioredis import FakeRedis

from src.grouping_service import GroupingService
from src.models import ProcessedUpdateMessage, PriorityEnum


@pytest.fixture
def mock_kafka_service():
    kafka_service = AsyncMock()
    kafka_service.output_topic = "test.processed-updates"

    async def fake_serialize(data):
        return json.dumps(data).encode("utf-8")

    kafka_service.serialize.side_effect = fake_serialize

    return kafka_service


@pytest_asyncio.fixture
async def grouping_service(mock_kafka_service):
    service = GroupingService(mock_kafka_service)

    service.valkey_client = FakeRedis(decode_responses=True)
    service.window_seconds = 0.1

    yield service

    await service.valkey_client.aclose()


@pytest.mark.asyncio
async def test_multiple_updates_grouping(grouping_service, mock_kafka_service):
    """2 часть TC-2.1 Группировка нескольких обновлений."""
    msg1 = ProcessedUpdateMessage(
        id=1,
        url="http://example.com/1",
        description="First update",
        tgChatIds=[222],
        priority=PriorityEnum.LOW,
    )
    msg2 = ProcessedUpdateMessage(
        id=2,
        url="http://example.com/1",
        description="Second critical update",
        tgChatIds=[222],
        priority=PriorityEnum.HIGH,
    )

    await grouping_service.add_message(msg1)
    await grouping_service.add_message(msg2)

    await asyncio.sleep(0.2)

    pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if pending:
        await asyncio.gather(*pending)

    mock_kafka_service.send_message.assert_called_once()
    call_args = mock_kafka_service.send_message.call_args
    sent_data = json.loads(call_args.kwargs["value"].decode("utf-8"))

    assert "1. First update" in sent_data["description"]
    assert "2. Second critical update" in sent_data["description"]

    assert sent_data["priority"] == PriorityEnum.HIGH.value
    assert sent_data["id"] == 1


@pytest.mark.asyncio
async def test_single_update_no_grouping(grouping_service, mock_kafka_service):
    """2 часть TC-2.2 Одиночное обновление."""
    msg = ProcessedUpdateMessage(
        id=10,
        url="http://example.com/10",
        description="Single lonely update",
        tgChatIds=[333],
        priority=PriorityEnum.MEDIUM,
    )

    await grouping_service.add_message(msg)

    await asyncio.sleep(0.2)

    pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if pending:
        await asyncio.gather(*pending)

    mock_kafka_service.send_message.assert_called_once()
    call_args = mock_kafka_service.send_message.call_args
    sent_data = json.loads(call_args.kwargs["value"].decode("utf-8"))

    assert sent_data["description"] == "Single lonely update"
    assert sent_data["priority"] == PriorityEnum.MEDIUM.value
