import asyncio
import json
import structlog
from concurrent.futures import ProcessPoolExecutor
from pydantic import ValidationError

from src.config import config
from src.grouping_service import GroupingService
from src.models import ProcessedUpdateMessage, RawUpdateMessage
from src.processor import UpdateProcessor
from src.kafka_service import KafkaService

logger = structlog.getLogger(__name__)


def process_message(raw_data: dict) -> str | None:
    """
    Парсит JSON, валидирует Pydantic и прогоняет через CPU-bound логику процессора.
    """
    try:
        message = RawUpdateMessage(**raw_data)

        processor = UpdateProcessor()
        processed_msg = processor.process_update(message)

        if processed_msg:
            return processed_msg.model_dump_json()

    except ValidationError as e:
        logger.error("Ошибка валидации Pydantic", error=str(e), data=raw_data)
    except json.JSONDecodeError as e:
        logger.error("Ошибка парсинга JSON", error=str(e), data=raw_data)
    except Exception as e:
        logger.error("Непредвиденная ошибка в multiprocessing worker'е", error=str(e))

    return None


async def run_kafka_pipeline():
    kafka_service = KafkaService(
        bootstrap_servers=config.kafka_bootstrap_servers,
        group_id=config.kafka_group_id,
        input_topic=config.kafka_input_topic,
        output_topic=config.kafka_output_topic,
        schema_registry_url=config.kafka_schema_registry_url,
    )
    await kafka_service.start()
    grouping_service = GroupingService(kafka_service)

    loop = asyncio.get_running_loop()

    try:
        with ProcessPoolExecutor() as process_pool:
            logger.info(
                "Kafka Pipeline запущен",
                mode="multiprocessing",
                input_topic=config.kafka_input_topic,
            )

            async for msg in kafka_service.consume():
                raw_dict = await kafka_service.deserialize(msg.value)
                logger.info(
                    "Получено сырое сообщение",
                    partition=msg.partition,
                    offset=msg.offset,
                )

                processed_json_str = await loop.run_in_executor(
                    process_pool, process_message, raw_dict
                )

                if processed_json_str:
                    processed_msg = ProcessedUpdateMessage(
                        **json.loads(processed_json_str)
                    )
                    await grouping_service.add_message(processed_msg)

    finally:
        logger.info("Остановка сервисов...")
        await grouping_service.close()
        await kafka_service.stop()


if __name__ == "__main__":
    asyncio.run(run_kafka_pipeline())
