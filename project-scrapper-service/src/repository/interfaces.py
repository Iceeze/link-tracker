from datetime import datetime
from typing import Protocol
from src.schemas import LinkResponse


class ChatRepository(Protocol):
    """Интерфейс репозитория для работы с чатами."""

    async def get_all_chat_ids(self, limit: int = 10, offset: int = 0) -> list[int]:
        """Получить список всех зарегистрированных chat_id (с пагинацией)."""
        ...

    async def add_chat(self, chat_id: int) -> bool:
        """Добавить чат. Возвращает False, если чат уже существует."""
        ...

    async def remove_chat(self, chat_id: int) -> bool:
        """Удалить чат. Возвращает False, если чат не найден."""
        ...

    async def chat_exists(self, chat_id: int) -> bool:
        """Проверить существование чата."""
        ...


class LinkRepository(Protocol):
    """Интерфейс репозитория для работы со ссылками."""

    async def get_links(
        self, chat_id: int, limit: int = 10, offset: int = 0
    ) -> list[LinkResponse]:
        """Получить все ссылки для чата (с пагинацией)."""
        ...

    async def add_link(
        self, chat_id: int, url: str, tags: list[str] | None = None
    ) -> LinkResponse:
        """Добавить ссылку для чата."""
        ...

    async def update_link_updated_at(self, url: str, updated_at: datetime) -> bool:
        """Обновить поле updated_at для ссылки по URL. Вернуть True, если ссылка найдена."""
        ...

    async def remove_link(self, chat_id: int, url: str) -> LinkResponse | None:
        """Удалить ссылку из чата."""
        ...

    async def link_exists_for_chat(self, chat_id: int, url: str) -> bool:
        """Проверить, существует ли ссылка для чата."""
        ...
