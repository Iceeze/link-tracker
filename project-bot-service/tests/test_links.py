from aiogram.types import Message
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.fsm.context import FSMContext
from aiogram.filters.command import CommandObject

from src.bot.links import (
    process_url,
    process_tags,
    cmd_list,
    cmd_cancel,
    cmd_untrack,
)
from src.schemas import ListLinksResponse, LinkResponse
from src.bot.middlewares import CancelDialogMiddleware
from src.bot.links import UntrackStates


@pytest.fixture
def mock_state() -> AsyncMock:
    """Фикстура для имитации состояния FSM (хранилища)."""
    state = AsyncMock(spec=FSMContext)
    state.get_data = AsyncMock(return_value={"url": "https://github.com/user/repo"})
    return state


@pytest.mark.asyncio
@patch("src.bot.links.scrapper_client")
async def test_track_positive_saves_data(
    mock_scrapper, mock_message, mock_state
) -> None:
    """
    Пользователь отправляет /track и корректную ссылку, а затем теги.
    Ожидается: Данные сохранены в локальное хранилище (отправлены в Scrapper).
    """
    mock_message.text = "work, project"
    mock_scrapper.add_link = AsyncMock(return_value=(True, "Успех"))

    await process_tags(mock_message, mock_state)

    mock_scrapper.add_link.assert_called_once_with(
        12345, "https://github.com/user/repo", ["work", "project"]
    )

    sent_text = mock_message.answer.call_args[0][0]
    assert "добавлена в список" in sent_text


@pytest.mark.asyncio
async def test_track_incorrect_link(mock_message, mock_state) -> None:
    """
    Пользователь отправляет некорректную ссылку (tbank://github.com...).
    Ожидается: Бот уведомляет, что ссылка некорректна.
    """
    mock_message.text = "tbank://github.com/user/repo"

    await process_url(mock_message, mock_state)

    sent_text = mock_message.answer.call_args[0][0]
    assert "неподдерживаемая ссылка" in sent_text.lower()


@pytest.mark.asyncio
@patch("src.bot.links.scrapper_client")
async def test_track_already_tracked(mock_scrapper, mock_message, mock_state) -> None:
    """
    Пользователь отправляет ссылку, на которую уже подписан.
    Ожидается: Бот уведомляет, что уже подписан.
    """
    mock_message.text = "нет"
    mock_scrapper.add_link = AsyncMock(return_value=(False, "Ссылка уже отслеживается"))

    await process_tags(mock_message, mock_state)

    sent_text = mock_message.answer.call_args[0][0]
    assert "уже отслеживается" in sent_text.lower()


@pytest.mark.asyncio
@patch("src.bot.links.scrapper_client")
async def test_list_with_links(mock_scrapper, mock_message) -> None:
    """
    Запрос /list, есть активные подписки.
    Ожидается: Бот присылает список.
    """
    mock_scrapper.get_links = AsyncMock(
        return_value=ListLinksResponse(
            size=1,
            links=[
                LinkResponse(
                    id=1,
                    url="https://github.com/user/repo",
                    tags=[],
                    filters=[],
                    updated_at=None,
                )
            ],
        )
    )

    command = CommandObject(prefix="/", command="list", args=None)

    await cmd_list(mock_message, command)

    sent_text = mock_message.answer.call_args[0][0]
    assert "https://github.com/user/repo" in sent_text


@pytest.mark.asyncio
@patch("src.bot.links.scrapper_client")
async def test_list_empty(mock_scrapper, mock_message) -> None:
    """
    Запрос /list, нет активных подписок.
    Ожидается: Бот присылает сообщение об их отсутствии.
    """
    mock_scrapper.get_links = AsyncMock(
        return_value=ListLinksResponse(size=0, links=[])
    )
    command = CommandObject(prefix="/", command="list", args=None)

    await cmd_list(mock_message, command)

    sent_text = mock_message.answer.call_args[0][0]
    assert "не отслеживаете" in sent_text.lower()


@pytest.mark.asyncio
@patch("src.bot.links.scrapper_client")
async def test_list_with_tag(mock_scrapper, mock_message) -> None:
    """
    Запрос /list <tag>.
    Ожидается: Бот присылает список, отфильтрованный по тегу.
    """
    mock_scrapper.get_links = AsyncMock(
        return_value=ListLinksResponse(
            size=2,
            links=[
                LinkResponse(
                    id=1,
                    url="https://github.com/user/repo1",
                    tags=["work"],
                    filters=[],
                    updated_at=None,
                ),
                LinkResponse(
                    id=2,
                    url="https://github.com/user/repo2",
                    tags=["hobby"],
                    filters=[],
                    updated_at=None,
                ),
            ],
        )
    )

    command = CommandObject(prefix="/", command="list", args="work")

    await cmd_list(mock_message, command)

    sent_text = mock_message.answer.call_args[0][0]
    assert "https://github.com/user/repo1" in sent_text
    assert "https://github.com/user/repo2" not in sent_text


@pytest.mark.asyncio
async def test_cancel_during_dialog(mock_message, mock_state) -> None:
    """
    Тест /cancel во время диалога (например, waiting_for_url).
    Ожидается: состояние очищено, пользователь получает сообщение об отмене.
    """
    mock_state.get_state.return_value = "TrackStates:waiting_for_url"

    await cmd_cancel(mock_message, mock_state)

    mock_state.clear.assert_called_once()
    mock_message.answer.assert_called_once()
    sent_text = mock_message.answer.call_args[0][0]
    assert "отмена" in sent_text.lower()


@pytest.mark.asyncio
async def test_middleware_cancels_dialog_on_other_command(
    mock_state: AsyncMock,
) -> None:
    """
    При получении команды (не /cancel) и активном FSM-состоянии
    состояние должно быть сброшено, затем вызван хендлер.
    """
    middleware = CancelDialogMiddleware()
    mock_handler = AsyncMock()

    event = MagicMock(spec=Message)
    event.text = "/list"
    mock_state.get_state.return_value = "TrackStates:waiting_for_url"
    data = {"state": mock_state}

    await middleware(mock_handler, event, data)

    mock_state.clear.assert_called_once()
    mock_handler.assert_called_once_with(event, data)


@pytest.mark.asyncio
async def test_untrack_command(mock_message: MagicMock, mock_state: AsyncMock) -> None:
    """
    Тест команды /untrack.
    Ожидается: бот устанавливает состояние waiting_for_url (untrack)
    и отправляет приглашение ввести ссылку.
    """
    await cmd_untrack(mock_message, mock_state)

    mock_state.set_state.assert_called_once_with(UntrackStates.waiting_for_url)
    mock_message.answer.assert_called_once()
    sent_text = mock_message.answer.call_args[0][0]
    assert "перестать отслеживать" in sent_text.lower()
    assert "/cancel" in sent_text


@pytest.mark.asyncio
async def test_untrack_cancelled_by_other_command(
    mock_message: MagicMock, mock_state: AsyncMock
) -> None:
    """
    Активный диалог /untrack прерывается командой /track.
    Middleware сбрасывает состояние, отрабатывает cmd_track.
    """
    mock_state.get_state.return_value = "UntrackStates:waiting_for_url"

    middleware = CancelDialogMiddleware()
    event = MagicMock(spec=Message)
    event.text = "/track"
    event.from_user = mock_message.from_user
    event.answer = mock_message.answer
    data = {"state": mock_state}

    async def mock_cmd_track(message, state):
        await message.answer("трекер запущен")

    await middleware(mock_cmd_track, event, data)

    mock_state.clear.assert_called_once()
    mock_message.answer.assert_called_once_with("трекер запущен")
