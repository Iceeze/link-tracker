import httpx
from tenacity import retry, wait_fixed, stop_after_attempt, retry_if_exception
from datetime import datetime
from pydantic import BaseModel
import structlog

from src.config import load_config
from src.sre.utils import is_retryable_exception, timeout, breaker

logger = structlog.get_logger(__name__)
config = load_config()


class GithubRepoResponse(BaseModel):
    id: int
    full_name: str
    updated_at: datetime
    pushed_at: datetime


class GithubIssuePRItem(BaseModel):
    """Элемент списка Issues или Pull Requests."""

    id: int
    number: int
    title: str
    user_login: str
    created_at: datetime
    body: str | None = None
    html_url: str

    @property
    def preview(self) -> str:
        """Первые 200 символов описания."""
        if not self.body:
            return ""
        return self.body[:200]


class GithubClient:
    def __init__(self, base_url: str, token: str | None = None):
        self.base_url = base_url
        self.headers = {"Accept": "application/vnd.github.v3+json"}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    @retry(
        wait=wait_fixed(config.retry_wait_time),
        stop=stop_after_attempt(config.retry_stop_attempts),
        retry=retry_if_exception(is_retryable_exception),
        reraise=config.retry_reraise,
    )
    async def _make_request(
        self, client: httpx.AsyncClient, endpoint: str, params: dict | None = None
    ):
        """Одиночный запрос с логикой Retry."""
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
    async def fetch_repo(self, owner: str, repo: str) -> GithubRepoResponse:
        """Асинхронный запрос к API GitHub, возвращает информацию о репозитории."""
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers,
            follow_redirects=True,
            timeout=timeout,
        ) as client:
            response = await client.get(f"/repos/{owner}/{repo}")
            response.raise_for_status()
            return GithubRepoResponse(**response.json())

    @breaker
    async def _fetch_paginated_items(
        self,
        endpoint: str,
        owner: str,
        repo: str,
        batch_size: int,
        state: str = "all",
    ) -> list[GithubIssuePRItem]:
        """Загрузить все Issues или PRs с пагинацией."""
        all_items: list[GithubIssuePRItem] = []
        page = 1
        per_page = min(batch_size, 100)  # GitHub API максимум 100 на страницу

        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers,
            follow_redirects=True,
            timeout=timeout,
        ) as client:
            while True:
                params = {"state": state, "per_page": per_page, "page": page}
                endpoint_format = endpoint.format(owner=owner, repo=repo)
                response = await self._make_request(client, endpoint_format, params)
                data = response.json()
                if not data:
                    break

                for item in data:
                    all_items.append(
                        GithubIssuePRItem(
                            id=item["id"],
                            number=item["number"],
                            title=item["title"],
                            user_login=item["user"]["login"],
                            created_at=datetime.fromisoformat(
                                item["created_at"].replace("Z", "+00:00")
                            ),
                            body=item.get("body"),
                            html_url=item["html_url"],
                        )
                    )

                link_header = response.headers.get("link", "")
                if 'rel="next"' not in link_header:
                    break

                page += 1

        return all_items

    async def fetch_issues(
        self, owner: str, repo: str, batch_size: int = 100, state: str = "all"
    ) -> list[GithubIssuePRItem]:
        """Получить все Issues репозитория с пагинацией."""
        return await self._fetch_paginated_items(
            "/repos/{owner}/{repo}/issues", owner, repo, batch_size, state
        )

    async def fetch_pull_requests(
        self, owner: str, repo: str, batch_size: int = 100, state: str = "all"
    ) -> list[GithubIssuePRItem]:
        """Получить все Pull Requests репозитория с пагинацией."""
        return await self._fetch_paginated_items(
            "/repos/{owner}/{repo}/pulls", owner, repo, batch_size, state
        )

    @breaker
    @retry(
        wait=wait_fixed(config.retry_wait_time),
        stop=stop_after_attempt(config.retry_stop_attempts),
        retry=retry_if_exception(is_retryable_exception),
        reraise=config.retry_reraise,
    )
    async def fetch_item_details(
        self, owner: str, repo: str, item_number: int, is_pr: bool = False
    ) -> GithubIssuePRItem:
        """Получить детали конкретного Issue или PR."""
        endpoint = (
            f"/repos/{owner}/{repo}/pulls/{item_number}"
            if is_pr
            else f"/repos/{owner}/{repo}/issues/{item_number}"
        )

        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers,
            follow_redirects=True,
            timeout=timeout,
        ) as client:
            response = await self._make_request(client, endpoint)
            data = response.json()
            return GithubIssuePRItem(
                id=data["id"],
                number=data["number"],
                title=data["title"],
                user_login=data["user"]["login"],
                created_at=datetime.fromisoformat(
                    data["created_at"].replace("Z", "+00:00")
                ),
                body=data.get("body"),
                html_url=data["html_url"],
            )
