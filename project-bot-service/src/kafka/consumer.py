from aiogram import Bot
from pydantic import ValidationError
import structlog
import asyncio
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer
from confluent_kafka.serialization import SerializationContext, MessageField

from src.bot.utils import process_notification
from src.schemas import LinkUpdate

logger = structlog.get_logger(__name__)

PROCESSED_UPDATE_SCHEMA = """
{
  "type": "record",
  "name": "ProcessedUpdateMessage",
  "fields": [
    {"name": "id", "type": "long"},
    {"name": "url", "type": "string"},
    {"name": "description", "type": "string"},
    {"name": "tgChatIds", "type": {"type": "array", "items": "long"}},
    {"name": "priority", "type": "string"}
  ]
}
"""


class Consumer:
    """Класс для управления Kafka Consumer."""

    def __init__(
        self,
        bootstrap_servers: str,
        topic: str,
        dlq_topic: str,
        schema_registry_url: str,
        group_id: str,
        max_retries: int = 3,
    ):
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self.dlq_topic = dlq_topic
        self.max_retries = max_retries
        self.group_id = group_id

        sr_client = SchemaRegistryClient({"url": schema_registry_url})
        self.deserializer = AvroDeserializer(
            schema_registry_client=sr_client, schema_str=PROCESSED_UPDATE_SCHEMA
        )

        self.consumer = AIOKafkaConsumer(
            self.topic,
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.group_id,
            auto_offset_reset="earliest",
        )
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
        )

    async def start(self):
        await self.consumer.start()
        await self.producer.start()

    async def stop(self):
        await self.consumer.stop()
        await self.producer.stop()

    async def _send_to_dlq(self, raw_msg: bytes, reason: str):
        """Вспомогательный метод для отправки в DLQ с указанием причины."""
        try:
            headers = [("error_reason", reason.encode("utf-8"))]
            await self.producer.send_and_wait(
                self.dlq_topic, value=raw_msg, headers=headers
            )
            logger.info(
                "Сообщение отправлено в DLQ", topic=self.dlq_topic, reason=reason
            )
        except Exception as e:
            logger.error(
                "Не удалось отправить сообщение в DLQ",
                topic=self.dlq_topic,
                error=str(e),
            )

    async def consume(self, bot: Bot):
        try:
            async for msg in self.consumer:
                raw_data = msg.value

                if not raw_data:
                    continue

                try:
                    ctx = SerializationContext(msg.topic, MessageField.VALUE)
                    notification_data = self.deserializer(raw_data, ctx)
                except Exception as e:
                    logger.error(
                        "Ошибка десериализации сообщения из Kafka", error=str(e)
                    )
                    await self._send_to_dlq(raw_data, f"deserialization_error: {e}")
                    continue

                try:
                    update = LinkUpdate(**notification_data)
                except ValidationError as e:
                    logger.error(
                        "Ошибка валидации сообщения из Kafka",
                        error=str(e),
                        data=notification_data,
                    )
                    await self._send_to_dlq(raw_data, "validation_error")
                    continue

                for attempt in range(1, self.max_retries + 1):
                    try:
                        delivered = await process_notification(update, bot)
                        if not delivered:
                            raise RuntimeError("notification was not delivered")
                        break

                    except Exception as e:
                        logger.error(
                            "Ошибка при обработке сообщения",
                            attempt=attempt,
                            max_retries=self.max_retries,
                            error=str(e),
                        )

                        if attempt == self.max_retries:
                            logger.error(
                                "Исчерпаны попытки обработки сообщения. Отправка в DLQ."
                            )
                            await self._send_to_dlq(raw_data, f"processing_error: {e}")
                        else:
                            await asyncio.sleep(1)

        except asyncio.CancelledError:
            logger.info("Остановка Kafka Consumer...")


async def consume_notifications(consumer: Consumer, bot: Bot) -> None:
    await consumer.start()
    try:
        await consumer.consume(bot)
    finally:
        await consumer.stop()
        logger.info("Kafka Consumer успешно остановлен")
