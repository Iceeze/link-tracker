import httpx
import structlog
from aiokafka import AIOKafkaProducer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.serialization import SerializationContext, MessageField

from src.config import Settings, load_config
from src.schemas import LinkUpdateRequest, LinkResponse
from src.services.interfaces import NotificationService

logger = structlog.get_logger(__name__)
config = load_config()

timeout = httpx.Timeout(config.request_timeout, connect=config.request_timeout_connect)

LINK_UPDATE_EVENT_SCHEMA = """
{
  "type": "record",
  "name": "RawUpdateMessage",
  "fields": [
    {"name": "id", "type": "long"},
    {"name": "url", "type": "string"},
    {"name": "author", "type": "string"},
    {"name": "description", "type": "string"},
    {"name": "tgChatIds", "type": {"type": "array", "items": "long"}}
  ]
}
"""


class HTTPNotificationService(NotificationService):
    """HTTP-реализация сервиса отправки уведомлений."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def send_update(
        self, chat_id: int, link: LinkResponse, author: str, description: str
    ) -> bool:
        """Отправить уведомление об изменении по ссылке."""
        link_url = str(link.url)

        batch_request = LinkUpdateRequest(
            id=link.id,
            url=link_url,
            author=author,
            description=description,
            tgChatIds=[chat_id],
        )

        async with httpx.AsyncClient(base_url=self.base_url, timeout=timeout) as client:
            try:
                response = await client.post(
                    "/updates",
                    json=batch_request.model_dump(mode="json", exclude_none=True),
                )
                response.raise_for_status()
                logger.info(
                    "Уведомление успешно отправлено",
                    chat_id=chat_id,
                    url=link_url,
                    description_length=len(description),
                )
                return True
            except httpx.HTTPError as e:
                logger.error(
                    "Ошибка при отправке пакета уведомлений",
                    chat_id=chat_id,
                    url=link_url,
                    error=str(e),
                )
                return False


class KafkaNotificationService(NotificationService):
    """Kafka-реализация сервиса отправки уведомлений."""

    def __init__(self, bootstrap_servers: str, topic: str, schema_registry_url: str):
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic

        sr_client = SchemaRegistryClient({"url": schema_registry_url})
        self.avro_serializer = AvroSerializer(
            schema_registry_client=sr_client, schema_str=LINK_UPDATE_EVENT_SCHEMA
        )

        self.producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap_servers,
        )

    async def start(self):
        await self.producer.start()

    async def stop(self):
        await self.producer.stop()

    async def send_update(
        self, chat_id: int, link: LinkResponse, author: str, description: str
    ) -> bool:
        link_url = str(link.url)

        batch_request = LinkUpdateRequest(
            id=link.id,
            url=link_url,
            author=author,
            description=description,
            tgChatIds=[chat_id],
        )

        try:
            ctx = SerializationContext(self.topic, MessageField.VALUE)
            serialized_value = self.avro_serializer(
                batch_request.model_dump(mode="json", exclude_none=True), ctx
            )
            await self.producer.send_and_wait(
                self.topic,
                value=serialized_value,
            )
            logger.info(
                "Kafka сообщение успешно отправлено",
                chat_id=chat_id,
                link_id=link.id,
                topic=self.topic,
            )
            return True
        except Exception as e:
            logger.error(
                "Не удалось отправить сообщение в Kafka",
                chat_id=chat_id,
                link_id=link.id,
                error=str(e),
            )
            return False


class FallbackNotificationService(NotificationService):
    """Сервис-обертка: сначала пытается отправить через primary,
    при неудаче — через secondary.
    """

    def __init__(self, primary: NotificationService, secondary: NotificationService):
        self.primary = primary
        self.secondary = secondary

    async def start(self) -> None:
        """Запуск необходимых ресурсов."""
        for service in (self.primary, self.secondary):
            if hasattr(service, "start"):
                await service.start()

    async def stop(self) -> None:
        """Остановка ресурсов."""
        for service in (self.primary, self.secondary):
            if hasattr(service, "stop"):
                await service.stop()

    async def send_update(
        self, chat_id: int, link: LinkResponse, author: str, description: str
    ) -> bool:
        success = await self.primary.send_update(chat_id, link, author, description)

        if success:
            return True

        logger.warning(
            "Основной канал уведомлений недоступен. Переход на Fallback-канал.",
            chat_id=chat_id,
            link_id=link.id,
        )

        return await self.secondary.send_update(chat_id, link, author, description)


def get_notification_service(config: Settings) -> NotificationService:
    """Фабрика для создания экземпляра NotificationService на основе конфигурации."""
    http_service = HTTPNotificationService(config.bot_base_url)

    if config.notification_method == "KAFKA":
        kafka_service = KafkaNotificationService(
            config.kafka_bootstrap_servers,
            config.kafka_topic,
            config.kafka_schema_registry_url,
        )
        if config.use_fallback_notification:
            return FallbackNotificationService(kafka_service, http_service)
        return kafka_service

    return http_service
