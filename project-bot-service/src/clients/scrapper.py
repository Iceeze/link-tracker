import httpx
from pydantic import ValidationError

from src.config import config
from src.schemas import ListLinksResponse


class ScrapperClient:
    def __init__(self) -> None:
        self.base_url = config.scrapper_base_url
        self.timeout = 5.0

    async def register_chat(self, chat_id: int) -> bool:
        """Регистрирует чат в Скраппере."""
        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=self.timeout
        ) as client:
            response = await client.post(f"/tg-chat/{chat_id}")
            return response.status_code == 200

    async def get_links(self, chat_id: int) -> ListLinksResponse | None:
        """Получает список ссылок для указанного чата."""
        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=self.timeout
        ) as client:
            try:
                response = await client.get(
                    "/links", headers={"Tg-Chat-Id": str(chat_id)}
                )
                response.raise_for_status()
                return ListLinksResponse.model_validate(response.json())
            except (httpx.HTTPError, ValueError, ValidationError):
                return None

    async def add_link(
        self, chat_id: int, url: str, tags: list[str] | None
    ) -> tuple[bool, str]:
        """Добавляет ссылку для отслеживания."""
        payload = {"link": url, "tags": tags or [], "filters": []}
        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=self.timeout
        ) as client:
            try:
                response = await client.post(
                    "/links", headers={"Tg-Chat-Id": str(chat_id)}, json=payload
                )
                response.raise_for_status()
                return True, "Ссылка успешно добавлена."
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    return False, "Чат не существует."
                if e.response.status_code == 409:
                    return False, "Ссылка уже отслеживается."
                return False, "Произошла ошибка при добавлении."

    async def remove_link(self, chat_id: int, url: str) -> bool:
        """Удаляет ссылку из отслеживания."""
        payload = {"link": url}
        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=self.timeout
        ) as client:
            response = await client.request(
                "DELETE", "/links", headers={"Tg-Chat-Id": str(chat_id)}, json=payload
            )
            return response.status_code == 200


scrapper_client = ScrapperClient()
