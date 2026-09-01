from datetime import datetime

from src.repository.interfaces import ChatRepository, LinkRepository
from src.schemas import LinkResponse
from src.services.interfaces import LinkService
from src.exceptions import ChatNotFoundException, LinkNotFoundException


class LinkServiceImpl(LinkService):
    """Реализация сервиса для работы со ссылками."""

    def __init__(
        self,
        chat_repo: ChatRepository,
        link_repo: LinkRepository,
    ) -> None:
        self.chat_repo = chat_repo
        self.link_repo = link_repo

    async def get_links(
        self, chat_id: int, limit: int = 10, offset: int = 0
    ) -> list[LinkResponse]:
        if not await self.chat_repo.chat_exists(chat_id):
            raise ChatNotFoundException(chat_id)
        return await self.link_repo.get_links(chat_id, limit, offset)

    async def add_link(
        self, chat_id: int, url: str, tags: list[str] | None = None
    ) -> LinkResponse:
        if not await self.chat_repo.chat_exists(chat_id):
            raise ChatNotFoundException(chat_id)
        return await self.link_repo.add_link(chat_id, url, tags)

    async def update_link_updated_at(
        self, chat_id: int, url: str, updated_at: datetime
    ) -> bool:
        if not await self.chat_repo.chat_exists(chat_id):
            raise ChatNotFoundException(chat_id)
        return await self.link_repo.update_link_updated_at(url, updated_at)

    async def remove_link(self, chat_id: int, url: str) -> LinkResponse | None:
        if not await self.chat_repo.chat_exists(chat_id):
            raise ChatNotFoundException(chat_id)

        result = await self.link_repo.remove_link(chat_id, url)
        if not result:
            raise LinkNotFoundException(url)
        return result
