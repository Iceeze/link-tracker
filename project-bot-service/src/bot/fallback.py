from aiogram import Router
from aiogram.types import Message
import structlog

logger = structlog.get_logger(__name__)
fallback_router = Router()


@fallback_router.message()
async def unknown_message(message: Message) -> None:
    """Обработка неизвестных команд."""
    if message.from_user is None:
        return
    logger.warning(
        "Получена неизвестная команда", user_id=message.from_user.id, text=message.text
    )
    await message.answer(
        "Неизвестная команда. Воспользуйтесь /help, чтобы посмотреть список доступных команд."
    )
