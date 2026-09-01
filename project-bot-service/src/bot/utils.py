import structlog
from html import escape
from aiogram import Bot

from src.schemas import LinkUpdate

logger = structlog.get_logger(__name__)


async def process_notification(update: LinkUpdate, bot: Bot) -> bool:
    """Универсальная функция для рассылки уведомлений.

    Возвращает True, если хотя бы одно сообщение отправлено успешно, иначе False.
    """
    logger.info("Начало обработки обновления", link_id=update.id)

    priority_str = f" [{update.priority.value}]"
    message_text = (
        f"🔔 <b>Обновление!</b>"
        f'\n\nСсылка: <a href="{escape(update.url)}">{escape(update.url)}</a>'
        f"\n\nВ отслеживаемом ресурсе произошли изменения:\n<i>{escape(update.description)}</i>"
        f"\n\nПриоритет: <b>{priority_str}</b>"
    )

    success_sent_messages_cnt = 0

    for chat_id in update.tgChatIds:
        try:
            await bot.send_message(
                chat_id=chat_id, text=message_text, parse_mode="HTML"
            )
            success_sent_messages_cnt += 1
            logger.info("Уведомление отправлено", chat_id=chat_id)
        except Exception as e:
            logger.error(
                "Не удалось отправить уведомление", chat_id=chat_id, error=str(e)
            )

    if success_sent_messages_cnt == 0 and len(update.tgChatIds) > 0:
        logger.warning(
            "Не удалось доставить уведомление ни в один чат", link_id=update.id
        )
        return False

    return True
