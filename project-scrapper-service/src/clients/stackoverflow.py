import re
import httpx
from tenacity import retry, wait_fixed, stop_after_attempt, retry_if_exception
import structlog
from datetime import datetime, timezone
from pydantic import BaseModel

from src.config import load_config
from src.sre.utils import is_retryable_exception, timeout, breaker

logger = structlog.get_logger(__name__)
config = load_config()


class SOQuestionItem(BaseModel):
    question_id: int
    last_activity_date: int
    title: str = ""

    @property
    def updated_at(self) -> datetime:
        return datetime.fromtimestamp(self.last_activity_date, tz=timezone.utc)


class SOQuestionResponse(BaseModel):
    items: list[SOQuestionItem]
    has_more: bool = False


class SOAnswerItem(BaseModel):
    """Элемент ответа на StackOverflow."""

    answer_id: int
    question_id: int
    owner_display_name: str | None = None
    creation_date: int
    body: str = ""
    score: int = 0

    @property
    def created_at(self) -> datetime:
        return datetime.fromtimestamp(self.creation_date, tz=timezone.utc)

    @property
    def preview(self) -> str:
        """Первые 200 символов тела ответа."""
        text = re.sub(r"<[^>]+>", "", self.body)
        return text[:200]


class SOCommentItem(BaseModel):
    """Элемент комментария на StackOverflow."""

    comment_id: int
    post_id: int
    owner_display_name: str | None = None
    creation_date: int
    body: str = ""

    @property
    def created_at(self) -> datetime:
        return datetime.fromtimestamp(self.creation_date, tz=timezone.utc)

    @property
    def preview(self) -> str:
        """Первые 200 символов тела комментария."""
        text = re.sub(r"<[^>]+>", "", self.body)
        return text[:200]


class StackOverflowClient:
    def __init__(self, base_url: str):
        self.base_url = base_url

    @retry(
        wait=wait_fixed(config.retry_wait_time),
        stop=stop_after_attempt(config.retry_stop_attempts),
        retry=retry_if_exception(is_retryable_exception),
        reraise=config.retry_reraise,
    )
    async def _make_request(
        self, client: httpx.AsyncClient, endpoint: str, params: dict
    ):
        """Одиночный запрос к StackOverflow с логикой Retry."""
        response = await client.get(endpoint, params=params)
        response.raise_for_status()
        return response

    @breaker
    @retry(
        wait=wait_fixed(config.retry_wait_time),
        stop=stop_after_attempt(config.retry_stop_attempts),
        retry=retry_if_exception(is_retryable_exception),
        reraise=config.retry_reraise,
    )
    async def fetch_question(self, question_id: int) -> SOQuestionResponse | None:
        """Асинхронный запрос к API StackOverflow, возвращает информацию о вопросе."""
        async with httpx.AsyncClient(
            base_url=self.base_url, follow_redirects=True, timeout=timeout
        ) as client:
            endpoint = f"/questions/{question_id}"
            params = {"site": "stackoverflow"}
            response = await self._make_request(client, endpoint, params)
            data = response.json()
            if data.get("items"):
                return SOQuestionResponse(**data)

            return None

    @breaker
    async def _fetch_paginated_items(
        self, endpoint: str, question_id: int, batch_size: int, min_date: int | None
    ) -> list[dict]:
        """Загрузить элементы с пагинацией (ответы или комментарии)."""
        all_items: list[dict] = []
        page = 1
        pagesize = min(batch_size, 100)  # SO API максимум 100 на страницу

        async with httpx.AsyncClient(
            base_url=self.base_url, follow_redirects=True, timeout=timeout
        ) as client:
            while True:
                params: dict = {
                    "site": "stackoverflow",
                    "page": page,
                    "pagesize": pagesize,
                    "filter": "withbody",
                }
                if min_date:
                    params["min"] = min_date

                endpoint_format = endpoint.format(question_id=question_id)

                response = await self._make_request(client, endpoint_format, params)
                data = response.json()
                items = data.get("items", [])
                if not items:
                    break

                all_items.extend(items)

                if not data.get("has_more", False):
                    break

                page += 1

        return all_items

    async def fetch_answers(
        self,
        question_id: int,
        batch_size: int = 100,
        min_date: datetime | None = None,
    ) -> list[SOAnswerItem]:
        """Получить все ответы на вопрос с пагинацией."""
        min_timestamp = int(min_date.timestamp()) if min_date else None

        items = await self._fetch_paginated_items(
            "/questions/{question_id}/answers", question_id, batch_size, min_timestamp
        )
        return [SOAnswerItem(**item) for item in items]

    async def fetch_comments(
        self,
        question_id: int,
        batch_size: int = 100,
        min_date: datetime | None = None,
    ) -> list[SOCommentItem]:
        """Получить все комментарии на вопрос с пагинацией."""
        min_timestamp = int(min_date.timestamp()) if min_date else None

        items = await self._fetch_paginated_items(
            "/questions/{question_id}/comments", question_id, batch_size, min_timestamp
        )
        return [SOCommentItem(**item) for item in items]

    @breaker
    @retry(
        wait=wait_fixed(config.retry_wait_time),
        stop=stop_after_attempt(config.retry_stop_attempts),
        retry=retry_if_exception(is_retryable_exception),
        reraise=config.retry_reraise,
    )
    async def fetch_question_details(
        self, question_id: int
    ) -> SOQuestionResponse | None:
        """Получить детали вопроса."""
        async with httpx.AsyncClient(
            base_url=self.base_url, follow_redirects=True, timeout=timeout
        ) as client:
            endpoint = f"/questions/{question_id}"
            params = {"site": "stackoverflow", "filter": "withbody"}
            response = await self._make_request(client, endpoint, params)
            data = response.json()
            if data.get("items"):
                return SOQuestionResponse(**data)

            return None
