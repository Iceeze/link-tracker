from datetime import datetime
from typing import Protocol

from src.schemas import LinkResponse


class ChatService(Protocol):
    """Интерфейс сервиса для работы с чатами."""

    async def register_chat(self, chat_id: int) -> bool:
        """Зарегистрировать чат. Возвращает False, если чат уже существует."""
        ...

    async def unregister_chat(self, chat_id: int) -> bool:
        """Удалить чат. Возвращает False, если чат не найден."""
        ...

    async def get_all_chats(self, limit: int = 10, offset: int = 0) -> list[int]:
        """Получить все зарегистрированные чаты."""
        ...


class LinkService(Protocol):
    """Интерфейс сервиса для работы со ссылками."""

    async def get_links(
        self, chat_id: int, limit: int = 10, offset: int = 0
    ) -> list[LinkResponse]:
        """Получить все ссылки для чата."""
        ...

    async def add_link(
        self, chat_id: int, url: str, tags: list[str] | None = None
    ) -> LinkResponse:
        """Добавить ссылку для чата."""
        ...

    async def update_link_updated_at(
        self, chat_id: int, url: str, updated_at: datetime
    ) -> bool:
        """Обновить время последнего обновления ссылки."""
        ...

    async def remove_link(self, chat_id: int, url: str) -> LinkResponse | None:
        """Удалить ссылку из чата."""
        ...


class NotificationService(Protocol):
    """Интерфейс сервиса отправки уведомлений scrapper → bot."""

    async def send_update(
        self, chat_id: int, link: LinkResponse, author: str, description: str
    ) -> bool:
        """Отправить уведомление об изменении по ссылке."""
        ...
