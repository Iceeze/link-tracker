import structlog
from fastapi import APIRouter, Depends, Request, status

from src.bot.utils import process_notification
from src.exceptions import BotApiException
from src.schemas import LinkUpdate

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["Updates"])


def get_bot(request: Request):
    """Достает бота из state приложения."""
    return request.app.state.bot


@router.post("/updates", status_code=status.HTTP_200_OK, summary="Отправить обновление")
async def handle_update(update: LinkUpdate, bot=Depends(get_bot)) -> dict[str, str]:
    """Эндпоинт, который вызывает Scrapper, когда находит обновление по ссылке."""
    logger.info("Получено обновление от Scrapper", link_id=update.id)

    success = await process_notification(update, bot)

    if not success:
        raise BotApiException(
            description="Не удалось доставить уведомление ни в один чат", code="400"
        )

    return {"status": "ok"}
