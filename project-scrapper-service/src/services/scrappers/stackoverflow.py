import structlog
from datetime import datetime
from urllib.parse import urlparse

from src.clients.stackoverflow import StackOverflowClient, SOAnswerItem, SOCommentItem
from src.schemas import LinkUpdateDetails, UpdateType
from src.services.scrappers.base import BaseScrapper

logger = structlog.get_logger(__name__)


class StackOverflowScrapper(BaseScrapper):
    """Scrapper для проверки StackOverflow вопросов на наличие новых ответов и комментариев."""

    def __init__(self, client: StackOverflowClient):
        self.client = client

    @staticmethod
    def parse_so_url(url: str) -> int | None:
        """Извлечь question_id из StackOverflow URL."""
        parsed = urlparse(url)
        if parsed.hostname != "stackoverflow.com":
            return None

        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "questions":
            try:
                return int(parts[1])
            except ValueError:
                return None
        return None

    async def check_for_updates(
        self, url: str, last_updated: datetime | None, batch_size: int
    ) -> list[LinkUpdateDetails]:
        question_id = self.parse_so_url(url)
        if question_id is None:
            logger.error("Не удалось распарсить StackOverflow URL", url=url)
            return []

        updates: list[LinkUpdateDetails] = []

        try:
            question_info = await self.client.fetch_question_details(question_id)
            question_title = (
                question_info.items[0].title
                if question_info and question_info.items
                else f"Вопрос #{question_id}"
            )

            answers = await self.client.fetch_answers(
                question_id, batch_size, min_date=last_updated
            )
            updates.extend(self._answers_to_updates(answers, question_title))

            comments = await self.client.fetch_comments(
                question_id, batch_size, min_date=last_updated
            )
            updates.extend(
                self._comments_to_updates(comments, question_title, question_id)
            )
        except Exception as e:
            logger.error("Ошибка при проверке StackOverflow", url=url, error=str(e))
            return []

        if updates:
            logger.info(
                "Найдены обновления StackOverflow",
                url=url,
                answers_count=len(
                    [u for u in updates if u.update_type == UpdateType.SO_ANSWER]
                ),
                comments_count=len(
                    [u for u in updates if u.update_type == UpdateType.SO_COMMENT]
                ),
            )

        return updates

    def _answers_to_updates(
        self, answers: list[SOAnswerItem], question_title: str
    ) -> list[LinkUpdateDetails]:
        """Конвертировать ответы в LinkUpdateDetails."""
        return [
            LinkUpdateDetails(
                update_type=UpdateType.SO_ANSWER,
                title=question_title,
                username=answer.owner_display_name or "Аноним",
                created_at=answer.created_at,
                preview=answer.preview,
                url=f"https://stackoverflow.com/a/{answer.answer_id}",
            )
            for answer in answers
        ]

    def _comments_to_updates(
        self,
        comments: list[SOCommentItem],
        question_title: str,
        question_id: int,
    ) -> list[LinkUpdateDetails]:
        """Конвертировать комментарии в LinkUpdateDetails."""
        return [
            LinkUpdateDetails(
                update_type=UpdateType.SO_COMMENT,
                title=question_title,
                username=comment.owner_display_name or "Аноним",
                created_at=comment.created_at,
                preview=comment.preview,
                url=f"https://stackoverflow.com/questions/{question_id}#comment-{comment.comment_id}",
            )
            for comment in comments
        ]
