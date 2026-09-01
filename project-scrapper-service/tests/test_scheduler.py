import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock

from src.schemas import UpdateType
from src.scheduler import check_updates, format_description

OLD_DATE = datetime(2020, 1, 1, tzinfo=timezone.utc)
NEW_DATE = datetime(2024, 1, 1, tzinfo=timezone.utc)
TIME_TOLERANCE = timedelta(seconds=10)


class TestCheckUpdates:
    """Тесты функции check_updates планировщика."""

    def _assert_updated_at_is_now(
        self, mock_link_service: AsyncMock, chat_id: int, url: str
    ) -> None:
        """Проверить, что update_link_updated_at вызван с текущим временем (±10 сек)."""
        mock_link_service.update_link_updated_at.assert_awaited_once()
        call_args = mock_link_service.update_link_updated_at.await_args
        assert call_args[0][0] == chat_id
        assert call_args[0][1] == url
        passed_time = call_args[0][2]
        now = datetime.now(tz=timezone.utc)
        assert now - TIME_TOLERANCE <= passed_time <= now + TIME_TOLERANCE

    @pytest.mark.asyncio
    async def test_check_updates_no_chats(
        self,
        mock_chat_service: AsyncMock,
        mock_link_service: AsyncMock,
        mock_notification_service: AsyncMock,
        scheduler_mocks,
    ) -> None:
        """Планировщик корректно завершает работу, если нет зарегистрированных чатов."""
        mock_chat_service.get_all_chats.return_value = []

        with scheduler_mocks():
            await check_updates(
                mock_chat_service, mock_link_service, mock_notification_service
            )

        mock_chat_service.get_all_chats.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_check_updates_no_links(
        self,
        mock_chat_service: AsyncMock,
        mock_link_service: AsyncMock,
        mock_notification_service: AsyncMock,
        scheduler_mocks,
    ) -> None:
        """Планировщик не отправляет уведомления, если у чата нет ссылок."""
        mock_chat_service.get_all_chats.side_effect = [[111], []]
        mock_link_service.get_links.return_value = []

        with scheduler_mocks():
            await check_updates(
                mock_chat_service, mock_link_service, mock_notification_service
            )

        assert mock_chat_service.get_all_chats.await_count == 2
        mock_link_service.get_links.assert_awaited_once_with(111, limit=100, offset=0)

    @pytest.mark.asyncio
    async def test_check_updates_github_sends_notification(
        self,
        mock_chat_service: AsyncMock,
        mock_link_service: AsyncMock,
        mock_notification_service: AsyncMock,
        mock_github_scrapper: AsyncMock,
        scheduler_mocks,
        make_link,
        make_update_details,
    ) -> None:
        """Планировщик отправляет уведомление об обновлении GitHub репозитория."""
        url = "https://github.com/tiangolo/fastapi"
        mock_chat_service.get_all_chats.side_effect = [[111], []]

        link = make_link(link_id=1, url=url, updated_at=OLD_DATE)
        mock_link_service.get_links.side_effect = [[link], []]

        update_details = [
            make_update_details(
                update_type=UpdateType.GITHUB_PR,
                title="New PR",
                username="user1",
                created_at=NEW_DATE,
                url=f"{url}/pull/1",
            )
        ]
        mock_github_scrapper.check_for_updates.return_value = update_details
        expected_description = format_description(update_details[0])

        with scheduler_mocks():
            await check_updates(
                mock_chat_service, mock_link_service, mock_notification_service
            )

        mock_github_scrapper.check_for_updates.assert_awaited_once()
        mock_notification_service.send_update.assert_awaited_once_with(
            111, link, "user1", expected_description
        )
        self._assert_updated_at_is_now(mock_link_service, 111, url)

    @pytest.mark.asyncio
    async def test_check_updates_github_no_updates(
        self,
        mock_chat_service: AsyncMock,
        mock_link_service: AsyncMock,
        mock_notification_service: AsyncMock,
        mock_github_scrapper: AsyncMock,
        scheduler_mocks,
        make_link,
    ) -> None:
        """Планировщик не отправляет уведомление, если GitHub скраппер не нашёл обновлений."""
        url = "https://github.com/tiangolo/fastapi"
        mock_chat_service.get_all_chats.side_effect = [[111], []]

        link = make_link(link_id=1, url=url, updated_at=OLD_DATE)
        mock_link_service.get_links.side_effect = [[link], []]
        mock_github_scrapper.check_for_updates.return_value = []

        with scheduler_mocks():
            await check_updates(
                mock_chat_service, mock_link_service, mock_notification_service
            )

        mock_github_scrapper.check_for_updates.assert_awaited_once()
        mock_notification_service.send_update.assert_not_awaited()
        mock_link_service.update_link_updated_at.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_check_updates_stackoverflow_sends_notification(
        self,
        mock_chat_service: AsyncMock,
        mock_link_service: AsyncMock,
        mock_notification_service: AsyncMock,
        mock_stackoverflow_scrapper: AsyncMock,
        scheduler_mocks,
        make_link,
        make_update_details,
    ) -> None:
        """Планировщик отправляет уведомление об обновлении StackOverflow вопроса."""
        url = "https://stackoverflow.com/questions/12345"
        mock_chat_service.get_all_chats.side_effect = [[222], []]

        link = make_link(link_id=2, url=url, tags=["python"], updated_at=OLD_DATE)
        mock_link_service.get_links.side_effect = [[link], []]

        update_details = [
            make_update_details(
                update_type=UpdateType.SO_ANSWER,
                title="New Answer",
                username="expert42",
                created_at=NEW_DATE,
                url="https://stackoverflow.com/a/67890",
            )
        ]
        mock_stackoverflow_scrapper.check_for_updates.return_value = update_details
        expected_description = format_description(update_details[0])

        with scheduler_mocks():
            await check_updates(
                mock_chat_service, mock_link_service, mock_notification_service
            )

        mock_stackoverflow_scrapper.check_for_updates.assert_awaited_once()
        mock_notification_service.send_update.assert_awaited_once_with(
            222, link, "expert42", expected_description
        )
        self._assert_updated_at_is_now(mock_link_service, 222, url)

    @pytest.mark.asyncio
    async def test_check_updates_stackoverflow_no_updates(
        self,
        mock_chat_service: AsyncMock,
        mock_link_service: AsyncMock,
        mock_notification_service: AsyncMock,
        mock_stackoverflow_scrapper: AsyncMock,
        scheduler_mocks,
        make_link,
    ) -> None:
        """Планировщик не отправляет уведомление, если SO скраппер не нашёл обновлений."""
        url = "https://stackoverflow.com/questions/12345"
        mock_chat_service.get_all_chats.side_effect = [[222], []]

        link = make_link(link_id=2, url=url, updated_at=OLD_DATE)
        mock_link_service.get_links.side_effect = [[link], []]
        mock_stackoverflow_scrapper.check_for_updates.return_value = []

        with scheduler_mocks():
            await check_updates(
                mock_chat_service, mock_link_service, mock_notification_service
            )

        mock_stackoverflow_scrapper.check_for_updates.assert_awaited_once()
        mock_notification_service.send_update.assert_not_awaited()
        mock_link_service.update_link_updated_at.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_check_updates_notification_failure(
        self,
        mock_chat_service: AsyncMock,
        mock_link_service: AsyncMock,
        mock_notification_service: AsyncMock,
        mock_github_scrapper: AsyncMock,
        scheduler_mocks,
        make_link,
        make_update_details,
    ) -> None:
        """Планировщик не обновляет ссылку, если отправка уведомлений не удалась."""
        url = "https://github.com/tiangolo/fastapi"
        mock_chat_service.get_all_chats.side_effect = [[111], []]

        link = make_link(link_id=1, url=url, updated_at=OLD_DATE)
        mock_link_service.get_links.side_effect = [[link], []]

        update_details = [
            make_update_details(
                update_type=UpdateType.GITHUB_ISSUE,
                title="New Issue",
                username="dev",
                created_at=NEW_DATE,
                url=f"{url}/issues/100",
            )
        ]
        mock_github_scrapper.check_for_updates.return_value = update_details
        mock_notification_service.send_update.return_value = False

        with scheduler_mocks():
            await check_updates(
                mock_chat_service, mock_link_service, mock_notification_service
            )

        mock_notification_service.send_update.assert_awaited_once()
        mock_link_service.update_link_updated_at.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_check_updates_multiple_chats(
        self,
        mock_chat_service: AsyncMock,
        mock_link_service: AsyncMock,
        mock_notification_service: AsyncMock,
        mock_github_scrapper: AsyncMock,
        mock_stackoverflow_scrapper: AsyncMock,
        scheduler_mocks,
        make_link,
        make_update_details,
    ) -> None:
        """Планировщик обрабатывает несколько чатов с разными ссылками."""
        github_url = "https://github.com/tiangolo/fastapi"
        so_url = "https://stackoverflow.com/questions/12345"

        mock_chat_service.get_all_chats.side_effect = [[111, 222], []]

        link_github = make_link(link_id=1, url=github_url, updated_at=OLD_DATE)
        link_so = make_link(link_id=2, url=so_url, updated_at=OLD_DATE)

        mock_link_service.get_links.side_effect = [[link_github], [], [link_so], []]

        github_updates = [
            make_update_details(
                update_type=UpdateType.GITHUB_PR,
                title="PR",
                username="user",
                created_at=NEW_DATE,
                url=f"{github_url}/pull/1",
            )
        ]
        so_updates = [
            make_update_details(
                update_type=UpdateType.SO_ANSWER,
                title="Answer",
                username="expert",
                created_at=NEW_DATE,
                url="https://stackoverflow.com/a/100",
            )
        ]

        async def check_for_updates_side_effect(url: str, last_updated, batch_size):
            if "github.com" in url:
                return github_updates
            elif "stackoverflow.com" in url:
                return so_updates
            return []

        mock_github_scrapper.check_for_updates.side_effect = (
            check_for_updates_side_effect
        )
        mock_stackoverflow_scrapper.check_for_updates.side_effect = (
            check_for_updates_side_effect
        )
        mock_notification_service.send_update.return_value = True

        with scheduler_mocks():
            await check_updates(
                mock_chat_service, mock_link_service, mock_notification_service
            )

        assert mock_notification_service.send_update.await_count == 2
        assert mock_link_service.update_link_updated_at.await_count == 2


class TestFormatUpdateDescription:
    """Тесты функции format_update_description."""

    def test_single_github_pr_update(self, make_update_details) -> None:
        """Форматирование одного обновления GitHub PR."""
        updates = [
            make_update_details(
                update_type=UpdateType.GITHUB_PR,
                title="Add authentication",
                username="dev_user",
                preview="Implemented OAuth2 authentication flow",
                url="https://github.com/org/repo/pull/42",
                created_at=NEW_DATE,
            )
        ]

        result = format_description(updates[0])

        expected = (
            f"{NEW_DATE}\n"
            "GITHUB PR: Add authentication by @dev_user\n"
            "  Preview: Implemented OAuth2 authentication flow\n"
            "  URL: https://github.com/org/repo/pull/42"
        )
        assert result == expected

    def test_single_github_issue_update(self, make_update_details) -> None:
        """Форматирование одного обновления GitHub Issue."""
        updates = [
            make_update_details(
                update_type=UpdateType.GITHUB_ISSUE,
                title="Bug in login form",
                username="tester123",
                preview="Users cannot login with special characters",
                url="https://github.com/org/repo/issues/15",
                created_at=NEW_DATE,
            )
        ]

        result = format_description(updates[0])

        expected = (
            f"{NEW_DATE}\n"
            "GITHUB ISSUE: Bug in login form by @tester123\n"
            "  Preview: Users cannot login with special characters\n"
            "  URL: https://github.com/org/repo/issues/15"
        )
        assert result == expected

    def test_single_so_answer_update(self, make_update_details) -> None:
        """Форматирование одного обновления StackOverflow Answer."""
        updates = [
            make_update_details(
                update_type=UpdateType.SO_ANSWER,
                title="How to use FastAPI?",
                username="python_expert",
                preview="Here is a complete example with async...",
                url="https://stackoverflow.com/a/12345",
                created_at=NEW_DATE,
            )
        ]

        result = format_description(updates[0])

        expected = (
            f"{NEW_DATE}\n"
            "SO ANSWER: How to use FastAPI? by @python_expert\n"
            "  Preview: Here is a complete example with async...\n"
            "  URL: https://stackoverflow.com/a/12345"
        )
        assert result == expected

    def test_single_so_comment_update(self, make_update_details) -> None:
        """Форматирование одного обновления StackOverflow Comment."""
        updates = [
            make_update_details(
                update_type=UpdateType.SO_COMMENT,
                title="Database migration issue",
                username="dba_guru",
                preview="Have you tried running alembic upgrade head?",
                url="https://stackoverflow.com/questions/99999#comment",
                created_at=NEW_DATE,
            )
        ]

        result = format_description(updates[0])

        expected = (
            f"{NEW_DATE}\n"
            "SO COMMENT: Database migration issue by @dba_guru\n"
            "  Preview: Have you tried running alembic upgrade head?\n"
            "  URL: https://stackoverflow.com/questions/99999#comment"
        )
        assert result == expected

    def test_update_without_preview(self, make_update_details) -> None:
        """Обновление без preview не включает строку Preview."""
        updates = [
            make_update_details(
                update_type=UpdateType.GITHUB_PR,
                title="Update dependencies",
                username="bot",
                preview="",
                url="https://github.com/org/repo/pull/100",
                created_at=NEW_DATE,
            )
        ]

        result = format_description(updates[0])

        expected = (
            f"{NEW_DATE}\n"
            "GITHUB PR: Update dependencies by @bot\n"
            "  URL: https://github.com/org/repo/pull/100"
        )
        assert result == expected
