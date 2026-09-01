import asyncio
import contextlib
import traceback
from fastapi.concurrency import asynccontextmanager
from fastapi.responses import JSONResponse
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from aiogram import Bot, Dispatcher
import structlog

from src.bot.middlewares import CancelDialogMiddleware
from src.exceptions import BotApiException
from src.bot.base import base_router, set_commands
from src.bot.links import links_router
from src.bot.fallback import fallback_router
from src.bot.errors import error_router
from src.api.updates import router as api_router
from src.kafka import Consumer, consume_notifications
from src.schemas import ApiErrorResponse
from src.config import Settings

logger = structlog.get_logger(__name__)


def create_app(config: Settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        bot = Bot(token=config.bot_token)
        dp = Dispatcher()
        dp.include_router(base_router)
        dp.include_router(links_router)
        dp.include_router(fallback_router)
        dp.include_router(error_router)

        dp.message.outer_middleware(CancelDialogMiddleware())

        await set_commands(bot, config.bot_commands)
        app.state.bot = bot

        consumer_task = None
        if config.notification_method == "KAFKA":
            consumer = Consumer(
                bootstrap_servers=config.kafka_bootstrap_servers,
                topic=config.kafka_topic,
                dlq_topic=config.kafka_dlq_topic,
                schema_registry_url=config.kafka_schema_registry_url,
                group_id=config.kafka_group_id,
                max_retries=config.kafka_max_retries,
            )
            logger.info(
                "Запуск фонового процесса Kafka Consumer...",
                topic=config.kafka_topic,
                servers=config.kafka_bootstrap_servers,
            )
            consumer_task = asyncio.create_task(consume_notifications(consumer, bot))
        else:
            logger.info(
                "Режим Kafka отключен настройками. Бот ожидает уведомления только по HTTP.",
                method=config.notification_method,
            )

        logger.info("Запуск Telegram-бота (polling)...")
        polling_task = asyncio.create_task(dp.start_polling(bot))

        yield

        logger.info("Остановка Telegram-бота...")
        polling_task.cancel()

        with contextlib.suppress(asyncio.CancelledError, Exception):
            await polling_task

        if consumer_task is not None:
            consumer_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await consumer_task

        with contextlib.suppress(Exception):
            await bot.session.close()

    app = FastAPI(
        title="Bot API",
        description="API для приема уведомлений от Scrapper",
        lifespan=lifespan,
    )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Перехватчик ошибок валидации Pydantic."""
        logger.warning("Ошибка валидации входящего запроса", errors=exc.errors())
        error_response = ApiErrorResponse(
            description="Некорректные параметры запроса",
            code="400",
            exceptionName=exc.__class__.__name__,
            exceptionMessage=str(exc.errors()),
            stacktrace=traceback.format_exception(type(exc), exc, exc.__traceback__),
        )
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST, content=error_response.model_dump()
        )

    @app.exception_handler(BotApiException)
    async def bot_api_exception_handler(
        request: Request, exc: BotApiException
    ) -> JSONResponse:
        """Перехватчик кастомных ошибок BotApi."""
        error_response = ApiErrorResponse(
            description=exc.description,
            code=exc.code,
            exceptionName=exc.__class__.__name__,
            exceptionMessage=str(exc),
            stacktrace=traceback.format_exception(type(exc), exc, exc.__traceback__),
        )
        return JSONResponse(
            status_code=int(exc.code), content=error_response.model_dump()
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Перехватчик любых других непредвиденных ошибок."""
        logger.error("Внутренняя ошибка сервера", error=str(exc))
        error_response = ApiErrorResponse(
            description="Внутренняя ошибка сервера при обработке запроса",
            code="500",
            exceptionName=exc.__class__.__name__,
            exceptionMessage=str(exc),
            stacktrace=traceback.format_exception(type(exc), exc, exc.__traceback__),
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_response.model_dump(),
        )

    app.include_router(api_router)

    return app
