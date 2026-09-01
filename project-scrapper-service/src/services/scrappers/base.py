from datetime import datetime
from typing import Protocol

from src.schemas import LinkUpdateDetails


class BaseScrapper(Protocol):
    """Базовый интерфейс скраппера для проверки ссылок."""

    async def check_for_updates(
        self, url: str, last_updated: datetime | None, batch_size: int
    ) -> list[LinkUpdateDetails]:
        """
        Проверить ссылку на наличие изменений.

        Args:
            url: URL для проверки
            last_updated: Дата последнего известного обновления (None если новая ссылка)
            batch_size: Размер пакета для загрузки данных

        Returns:
            Список обнаруженных изменений
        """
        ...
