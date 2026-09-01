import structlog
from datetime import datetime
from urllib.parse import urlparse

from src.clients.github import GithubClient, GithubIssuePRItem
from src.schemas import LinkUpdateDetails, UpdateType
from src.services.scrappers.base import BaseScrapper

logger = structlog.get_logger(__name__)


class GithubScrapper(BaseScrapper):
    """Scrapper для проверки GitHub репозиториев на наличие новых PR и Issues."""

    def __init__(self, client: GithubClient):
        self.client = client

    @staticmethod
    def parse_github_url(url: str) -> tuple[str, str] | None:
        """Извлечь owner и repo из GitHub URL."""
        parsed = urlparse(url)
        if parsed.hostname != "github.com":
            return None

        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 2:
            return parts[0], parts[1]
        return None

    async def check_for_updates(
        self, url: str, last_updated: datetime | None, batch_size: int
    ) -> list[LinkUpdateDetails]:
        parsed = self.parse_github_url(url)
        if not parsed:
            logger.error("Не удалось распарсить GitHub URL", url=url)
            return []

        owner, repo = parsed
        updates: list[LinkUpdateDetails] = []

        try:
            prs = await self.client.fetch_pull_requests(owner, repo, batch_size)
            new_prs = self._filter_new_items(prs, last_updated)

            detailed_prs = await self._get_item_details(
                new_prs, owner, repo, is_pr=True
            )
            updates.extend(self._pr_to_updates(detailed_prs))

            issues = await self.client.fetch_issues(owner, repo, batch_size)
            pure_issues = [i for i in issues if f"/issues/{i.number}" in i.html_url]
            new_issues = self._filter_new_items(pure_issues, last_updated)

            detailed_issues = await self._get_item_details(
                new_issues, owner, repo, is_pr=False
            )
            updates.extend(self._issue_to_updates(detailed_issues))
        except Exception as e:
            logger.error("Ошибка при проверке GitHub", url=url, error=str(e))
            return []

        if updates:
            logger.info(
                "Найдены обновления GitHub",
                url=url,
                prs_count=len(
                    [u for u in updates if u.update_type == UpdateType.GITHUB_PR]
                ),
                issues_count=len(
                    [u for u in updates if u.update_type == UpdateType.GITHUB_ISSUE]
                ),
            )

        return updates

    async def _get_item_details(
        self,
        items: list[GithubIssuePRItem],
        owner: str,
        repo: str,
        is_pr: bool = False,
    ) -> list[GithubIssuePRItem]:
        """Получить детали элементов (с body) через отдельные запросы."""
        detailed_items: list[GithubIssuePRItem] = []
        for item in items:
            details = await self.client.fetch_item_details(
                owner, repo, item.number, is_pr=is_pr
            )
            if details:
                detailed_items.append(details)
            else:
                detailed_items.append(item)
        return detailed_items

    @staticmethod
    def _filter_new_items(
        items: list[GithubIssuePRItem], last_updated: datetime | None
    ) -> list[GithubIssuePRItem]:
        """Отфильтровать элементы созданные после last_updated.

        Для новых ссылок возвращается только последние 10 элементов, чтобы не спамить.
        """
        if last_updated is None:
            return items[-10:] if len(items) > 10 else items

        return [item for item in items if item.created_at > last_updated]

    def _pr_to_updates(self, prs: list[GithubIssuePRItem]) -> list[LinkUpdateDetails]:
        """Конвертировать PR в LinkUpdateDetails."""
        return [
            LinkUpdateDetails(
                update_type=UpdateType.GITHUB_PR,
                title=pr.title,
                username=pr.user_login,
                created_at=pr.created_at,
                preview=pr.preview,
                url=pr.html_url,
            )
            for pr in prs
        ]

    def _issue_to_updates(
        self, issues: list[GithubIssuePRItem]
    ) -> list[LinkUpdateDetails]:
        """Конвертировать Issues в LinkUpdateDetails."""
        return [
            LinkUpdateDetails(
                update_type=UpdateType.GITHUB_ISSUE,
                title=issue.title,
                username=issue.user_login,
                created_at=issue.created_at,
                preview=issue.preview,
                url=issue.html_url,
            )
            for issue in issues
        ]
