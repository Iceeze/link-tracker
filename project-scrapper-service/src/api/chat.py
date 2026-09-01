from fastapi import APIRouter, status, Request

from src.services import ChatService
from src.schemas import ApiErrorResponse
from src.sre.utils import limiter
from src.config import load_config

router = APIRouter(prefix="/tg-chat", tags=["Chats"])
config = load_config()


@router.post(
    "/{chat_id}",
    status_code=status.HTTP_200_OK,
    summary="Зарегистрировать чат",
    responses={
        400: {"model": ApiErrorResponse, "description": "Некорректные параметры"},
        409: {"model": ApiErrorResponse, "description": "Чат уже существует"},
    },
)
@limiter.limit(config.limiter_rate)
async def register_chat(request: Request, chat_id: int) -> dict[str, str]:
    """Зарегистрировать Telegram чат для отслеживания ссылок.

    - **chat_id**: ID Telegram чата
    """
    chat_service: ChatService = (
        request.app.state.repository_factory.create_chat_service()
    )

    await chat_service.register_chat(chat_id)
    return {"status": "Chat registered successfully"}


@router.delete(
    "/{chat_id}",
    status_code=status.HTTP_200_OK,
    summary="Удалить чат",
    responses={
        400: {"model": ApiErrorResponse, "description": "Некорректные параметры"},
        404: {"model": ApiErrorResponse, "description": "Чат не найден"},
    },
)
@limiter.limit(config.limiter_rate)
async def unregister_chat(request: Request, chat_id: int) -> dict[str, str]:
    """Удалить Telegram чат из системы отслеживания.

    - **chat_id**: ID Telegram чата
    """
    chat_service: ChatService = (
        request.app.state.repository_factory.create_chat_service()
    )

    await chat_service.unregister_chat(chat_id)
    return {"status": "Chat unregistered successfully"}
