import structlog
from aiogram import Router
from aiogram.types import ErrorEvent

logger = structlog.get_logger(__name__)
error_router = Router()


@error_router.error()
async def global_error_handler(event: ErrorEvent) -> None:
    """Глобальный обработчик ошибок для Telegram бота."""
    user_id = None
    if event.update.message and event.update.message.from_user:
        user_id = event.update.message.from_user.id
    elif event.update.callback_query and event.update.callback_query.from_user:
        user_id = event.update.callback_query.from_user.id

    logger.exception(
        "Handler error",
        error=str(event.exception),
        user_id=user_id,
        update_id=event.update.update_id,
    )
