import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from src.schemas import UpdateType
from src.clients.github import GithubIssuePRItem
from src.clients.stackoverflow import SOAnswerItem, SOCommentItem
from src.services.scrappers import GithubScrapper, StackOverflowScrapper


class TestGithubScrapperPreviewFormatting:
    """Тесты формирования превью из GitHub API ответов."""

    @pytest.mark.asyncio
    async def test_new_issue_creates_message_with_preview(self) -> None:
        """Scrapper формирует сообщение с названием, автором и превью для нового Issue."""
        issue_item = GithubIssuePRItem(
            id=12345,
            number=42,
            title="Critical bug in production",
            user_login="bug_reporter",
            created_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
            body="This is a detailed description of the bug with lots of information",
            html_url="https://github.com/org/repo/issues/42",
        )

        scrapper = GithubScrapper(AsyncMock())
        updates = scrapper._issue_to_updates([issue_item])

        assert len(updates) == 1
        update = updates[0]
        assert update.update_type == UpdateType.GITHUB_ISSUE
        assert update.title == "Critical bug in production"
        assert update.username == "bug_reporter"
        assert (
            update.preview
            == "This is a detailed description of the bug with lots of information"
        )
        assert update.url == "https://github.com/org/repo/issues/42"

    @pytest.mark.asyncio
    async def test_new_pr_creates_message_with_preview(self) -> None:
        """Scrapper формирует сообщение с названием, автором и превью для нового PR."""
        pr_item = GithubIssuePRItem(
            id=67890,
            number=100,
            title="Add new authentication feature",
            user_login="feature_dev",
            created_at=datetime(2024, 2, 20, tzinfo=timezone.utc),
            body="Implemented OAuth2 flow with JWT tokens and refresh token rotation",
            html_url="https://github.com/org/repo/pull/100",
        )

        scrapper = GithubScrapper(AsyncMock())
        updates = scrapper._pr_to_updates([pr_item])

        assert len(updates) == 1
        update = updates[0]
        assert update.update_type == UpdateType.GITHUB_PR
        assert update.title == "Add new authentication feature"
        assert update.username == "feature_dev"
        assert (
            update.preview
            == "Implemented OAuth2 flow with JWT tokens and refresh token rotation"
        )
        assert update.url == "https://github.com/org/repo/pull/100"

    @pytest.mark.asyncio
    async def test_issue_without_body_has_empty_preview(self) -> None:
        """Issue без body имеет пустое превью."""
        issue_item = GithubIssuePRItem(
            id=11111,
            number=5,
            title="Empty issue",
            user_login="anonymous",
            created_at=datetime(2024, 3, 1, tzinfo=timezone.utc),
            body=None,
            html_url="https://github.com/org/repo/issues/5",
        )

        scrapper = GithubScrapper(AsyncMock())
        updates = scrapper._issue_to_updates([issue_item])

        assert len(updates) == 1
        assert updates[0].preview == ""

    @pytest.mark.parametrize(
        "body_length,expected_preview_length",
        [
            (50, 50),
            (200, 200),
            (500, 200),
            (1000, 200),
        ],
    )
    @pytest.mark.asyncio
    async def test_preview_truncation_to_200_chars(
        self, body_length: int, expected_preview_length: int
    ) -> None:
        """Превью обрезается до 200 символов независимо от длины body."""
        body = "A" * body_length
        issue_item = GithubIssuePRItem(
            id=22222,
            number=10,
            title="Test",
            user_login="user",
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            body=body,
            html_url="https://github.com/test/repo/issues/10",
        )

        assert issue_item.preview == body[:200]
        assert len(issue_item.preview) == expected_preview_length


class TestStackOverflowScrapperPreviewFormatting:
    """Тесты формирования превью из StackOverflow API ответов."""

    @pytest.mark.asyncio
    async def test_new_answer_creates_message_with_preview(self) -> None:
        """Scrapper формирует сообщение с превью для нового ответа."""
        answer = SOAnswerItem(
            answer_id=77777,
            question_id=12345,
            owner_display_name="stackoverflow_expert",
            creation_date=1704067200,
            body="<p>Here is a complete solution to your problem using asyncio.</p>",
            score=5,
        )

        scrapper = StackOverflowScrapper(AsyncMock())
        updates = scrapper._answers_to_updates([answer], "Sample Question")

        assert len(updates) == 1
        update = updates[0]
        assert update.update_type == UpdateType.SO_ANSWER
        assert update.title == "Sample Question"
        assert update.username == "stackoverflow_expert"
        assert (
            update.preview
            == "Here is a complete solution to your problem using asyncio."
        )

    @pytest.mark.asyncio
    async def test_new_comment_creates_message_with_preview(self) -> None:
        """Scrapper формирует сообщение с превью для нового комментария."""
        comment = SOCommentItem(
            comment_id=99999,
            post_id=12345,
            owner_display_name="helpful_user",
            creation_date=1704067200,
            body="<p>Have you tried using <code>async/await</code>?</p>",
        )

        scrapper = StackOverflowScrapper(AsyncMock())
        updates = scrapper._comments_to_updates([comment], "Sample Question", 12345)

        assert len(updates) == 1
        update = updates[0]
        assert update.update_type == UpdateType.SO_COMMENT
        assert update.title == "Sample Question"
        assert update.username == "helpful_user"
        assert update.preview == "Have you tried using async/await?"

    @pytest.mark.asyncio
    async def test_preview_truncated_to_200_chars_so(self) -> None:
        """Превью ответа обрезается до 200 символов."""
        long_body = "<p>" + "A" * 300 + "</p>"
        answer = SOAnswerItem(
            answer_id=11111,
            question_id=99999,
            owner_display_name="verbose_user",
            creation_date=1704067200,
            body=long_body,
            score=0,
        )

        scrapper = StackOverflowScrapper(AsyncMock())
        updates = scrapper._answers_to_updates([answer], "Sample Question")

        assert len(updates) == 1
        assert len(updates[0].preview) == 200
        assert updates[0].preview == "A" * 200

    @pytest.mark.asyncio
    async def test_comment_preview_truncated_to_200_chars(self) -> None:
        """Превью комментария обрезается до 200 символов."""
        long_body = "B" * 500
        comment = SOCommentItem(
            comment_id=22222,
            post_id=88888,
            owner_display_name="user",
            creation_date=1704067200,
            body=long_body,
        )

        scrapper = StackOverflowScrapper(AsyncMock())
        updates = scrapper._comments_to_updates([comment], "Sample Question", 88888)

        assert len(updates) == 1
        assert len(updates[0].preview) == 200
        assert updates[0].preview == "B" * 200

    @pytest.mark.asyncio
    async def test_answer_with_empty_body_has_empty_preview(self) -> None:
        """Ответ с пустым body имеет пустое превью."""
        answer = SOAnswerItem(
            answer_id=33333,
            question_id=77777,
            owner_display_name="user",
            creation_date=1704067200,
            body="",
            score=0,
        )

        scrapper = StackOverflowScrapper(AsyncMock())
        updates = scrapper._answers_to_updates([answer], "Sample Question")

        assert len(updates) == 1
        assert updates[0].preview == ""

    @pytest.mark.asyncio
    async def test_comment_with_only_html_tags_has_empty_preview(self) -> None:
        """Комментарий только с HTML тегами имеет пустое превью."""
        comment = SOCommentItem(
            comment_id=44444,
            post_id=66666,
            owner_display_name="user",
            creation_date=1704067200,
            body="<br/><p></p>",
        )

        scrapper = StackOverflowScrapper(AsyncMock())
        updates = scrapper._comments_to_updates([comment], "Sample Question", 66666)

        assert len(updates) == 1
        assert updates[0].preview == ""
