import asyncio
import json
import structlog
from redis.asyncio import Redis

from src.config import config
from src.models import ProcessedUpdateMessage, PriorityEnum
from src.kafka_service import KafkaService

logger = structlog.getLogger(__name__)

PRIORITY_WEIGHT = {
    PriorityEnum.LOW: 1,
    PriorityEnum.MEDIUM: 2,
    PriorityEnum.HIGH: 3,
}


class GroupingService:
    def __init__(self, kafka_service: KafkaService):
        self.kafka_service = kafka_service
        self.valkey_client = Redis(
            host=config.valkey_host, port=config.valkey_port, decode_responses=True
        )
        self.window_seconds = config.grouping_window_ms / 1000

    async def close(self):
        await self.valkey_client.aclose()

    async def add_message(self, message: ProcessedUpdateMessage):
        """Расщепляет сообщение по чатам и добавляет в кэш."""
        for chat_id in message.tgChatIds:
            logger.info(
                "Добавление сообщения в группу",
                stage="grouping",
                chat_id=chat_id,
                message_id=message.id,
            )
            key = f"{chat_id}:{message.url}"

            msg_data = {
                "id": message.id,
                "url": message.url,
                "description": message.description,
                "priority": message.priority.value,
            }

            list_length = await self.valkey_client.rpush(key, json.dumps(msg_data))  # type: ignore[misc]

            # Если элемент первый, запускаем асинхронную задачу окна группировки
            if list_length == 1:
                ttl = max(1, int(self.window_seconds * 2))
                await self.valkey_client.expire(key, ttl)
                asyncio.create_task(self._flush_group_after_window(chat_id, key))

    async def _flush_group_after_window(self, chat_id: int, key: str):
        """Ждет окно группировки, собирает сообщения и отправляет в Kafka."""
        try:
            await asyncio.sleep(self.window_seconds)

            # Атомарно забираем все элементы и удаляем ключ через pipeline
            async with self.valkey_client.pipeline(transaction=True) as pipe:
                pipe.lrange(key, 0, -1)
                pipe.delete(key)
                results = await pipe.execute()

            raw_items = results[0]

            if not raw_items:
                return

            items = [json.loads(item) for item in raw_items]

            if len(items) == 1:
                item = items[0]
                final_description = item["description"]
                final_priority = PriorityEnum(item["priority"])
                msg_id = item["id"]
                url = item["url"]
            else:
                descriptions = []
                max_priority = PriorityEnum.LOW

                for idx, item in enumerate(items, start=1):
                    descriptions.append(f"{idx}. {item['description']}")
                    curr_priority = PriorityEnum(item["priority"])
                    if PRIORITY_WEIGHT[curr_priority] > PRIORITY_WEIGHT[max_priority]:
                        max_priority = curr_priority

                final_description = "\n".join(descriptions)
                final_priority = max_priority
                msg_id = items[0]["id"]
                url = items[0]["url"]

            grouped_message = ProcessedUpdateMessage(
                id=msg_id,
                url=url,
                description=final_description,
                tgChatIds=[chat_id],
                priority=final_priority,
            )

            topic = self.kafka_service.output_topic
            binary_data = await self.kafka_service.serialize(
                grouped_message.model_dump()
            )
            await self.kafka_service.send_message(topic, value=binary_data)
            logger.info(
                "Сгруппированное сообщение отправлено в Kafka",
                stage="grouping",
                chat_id=chat_id,
                count=len(items),
            )
        except Exception as e:
            logger.exception(
                "Ошибка группировки", stage="grouping", chat_id=chat_id, error=str(e)
            )
