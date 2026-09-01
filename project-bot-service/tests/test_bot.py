import pytest
from unittest.mock import MagicMock

from src.bot.base import cmd_start, cmd_help
from src.bot.fallback import unknown_message


@pytest.mark.asyncio
async def test_cmd_start_positive(mock_message: MagicMock) -> None:
    """Позитивный тест: При получении /start бот отвечает приветственным сообщением."""
    await cmd_start(mock_message)

    mock_message.answer.assert_called_once()
    sent_text = mock_message.answer.call_args[0][0]

    assert "Добро пожаловать!" in sent_text
    assert "Используйте /help" in sent_text


@pytest.mark.asyncio
async def test_cmd_help_positive(mock_message: MagicMock) -> None:
    """Позитивный тест: При получении /help бот отвечает описанием команд."""
    await cmd_help(mock_message)

    mock_message.answer.assert_called_once()
    sent_text = mock_message.answer.call_args[0][0]

    assert "Список доступных команд" in sent_text
    assert "/start" in sent_text
    assert "/help" in sent_text


@pytest.mark.asyncio
async def test_unknown_message_negative(mock_message: MagicMock) -> None:
    """Негативный тест: При получении неизвестной команды бот отвечает ошибкой."""
    mock_message.text = "/unknown"

    await unknown_message(mock_message)

    mock_message.answer.assert_called_once()
    sent_text = mock_message.answer.call_args[0][0]

    assert "Неизвестная команда" in sent_text
