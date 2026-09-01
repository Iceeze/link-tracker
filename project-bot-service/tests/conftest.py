import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture()
def mock_message() -> MagicMock:
    """Создание мок-сообщения с нужными атрибутами."""
    message = MagicMock()
    message.from_user.id = 12345
    message.answer = AsyncMock()
    return message
