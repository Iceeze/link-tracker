from fastapi import APIRouter, Request, status, Header

from src.clients import ValkeyClient
from src.schemas import (
    ApiErrorResponse,
    LinkResponse,
    ListLinksResponse,
    AddLinkRequest,
    RemoveLinkRequest,
)
from src.exceptions import LinkNotFoundException
from src.services import LinkService
from src.sre.utils import limiter
from src.config import load_config

router = APIRouter(prefix="/links", tags=["Links"])
config = load_config()


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    response_model=ListLinksResponse,
    responses={
        400: {"model": ApiErrorResponse, "description": "Некорректные параметры"},
        404: {"model": ApiErrorResponse, "description": "Чат не найден"},
    },
)
@limiter.limit(config.limiter_rate)
async def get_links(
    request: Request,
    tg_chat_id: int = Header(..., alias="Tg-Chat-Id", description="ID Telegram чата"),
    limit: int = 10,
    offset: int = 0,
) -> ListLinksResponse:
    """Получить все отслеживаемые ссылки для чата.

    - **Tg-Chat-Id**: ID Telegram чата (в заголовке)
    - **limit**: Максимальное количество ссылок для получения (по умолчанию 10)
    - **offset**: Смещение для пагинации (по умолчанию 0)
    """
    valkey: ValkeyClient = request.app.state.valkey_client
    cache_key = valkey.get_cache_key(tg_chat_id)

    cached_data = await valkey.get(cache_key)
    if cached_data:
        return ListLinksResponse.model_validate_json(cached_data)

    link_service: LinkService = (
        request.app.state.repository_factory.create_link_service()
    )

    links = await link_service.get_links(tg_chat_id, limit=limit, offset=offset)
    response = ListLinksResponse(links=links, size=len(links))

    await valkey.set(cache_key, response.model_dump_json(), ex=valkey.ttl)
    return response


@router.post(
    "",
    status_code=status.HTTP_200_OK,
    response_model=LinkResponse,
    responses={
        404: {"model": ApiErrorResponse, "description": "Чат не найден"},
        409: {"model": ApiErrorResponse, "description": "Ссылка уже существует"},
        400: {"model": ApiErrorResponse, "description": "Некорректные параметры"},
    },
)
@limiter.limit(config.limiter_rate)
async def add_link(
    request: Request,
    body: AddLinkRequest,
    tg_chat_id: int = Header(alias="Tg-Chat-Id", description="ID Telegram чата"),
) -> LinkResponse:
    """Добавить ссылку для отслеживания.

    - **Tg-Chat-Id**: ID Telegram чата (в заголовке)
    - **link**: URL ссылки
    - **tags**: Теги для ссылки (опционально)
    """
    link_service: LinkService = (
        request.app.state.repository_factory.create_link_service()
    )

    result = await link_service.add_link(
        chat_id=tg_chat_id,
        url=str(body.link),
        tags=body.tags,
    )

    valkey = request.app.state.valkey_client
    await valkey.delete(valkey.get_cache_key(tg_chat_id))

    return result


@router.delete(
    "",
    status_code=status.HTTP_200_OK,
    response_model=LinkResponse,
    responses={
        404: {"model": ApiErrorResponse, "description": "Чат или ссылка не найдены"},
        400: {"model": ApiErrorResponse, "description": "Некорректные параметры"},
    },
)
@limiter.limit(config.limiter_rate)
async def remove_link(
    request: Request,
    body: RemoveLinkRequest,
    tg_chat_id: int = Header(..., alias="Tg-Chat-Id", description="ID Telegram чата"),
) -> LinkResponse:
    """
    Удалить ссылку из отслеживания.

    - **Tg-Chat-Id**: ID Telegram чата (в заголовке)
    - **link**: URL ссылки для удаления
    """
    link_service: LinkService = (
        request.app.state.repository_factory.create_link_service()
    )

    result = await link_service.remove_link(
        chat_id=tg_chat_id,
        url=str(body.link),
    )
    if not result:
        raise LinkNotFoundException(str(body.link))

    valkey = request.app.state.valkey_client
    await valkey.delete(valkey.get_cache_key(tg_chat_id))

    return result
