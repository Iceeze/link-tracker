from unittest.mock import Mock, patch

import pytest
from src.models import PriorityEnum, RawUpdateMessage
from src.processor import UpdateProcessor
from src.config import config


@pytest.fixture
def processor():
    config.stop_words = ["spam", "ads"]
    config.excluded_authors = ["bot-user"]
    config.filter_min_length = 20
    config.summarization_threshold = 50
    config.hf_api_token = "fake_token"
    config.high_keywords = ["critical", "urgent"]
    config.low_keywords = ["minor", "typo"]
    return UpdateProcessor()


@pytest.fixture
def base_message():
    return RawUpdateMessage(
        id=1,
        url="http://example.com/update/1",
        description="Это длинное и валидное сообщение, которое точно пройдет фильтр длины.",
        author="good_user",
        tgChatIds=[111, 222],
    )


def test_filter_by_stop_word(processor, base_message):
    """1 часть TC-2.1 Фильтрация по стоп-словам."""
    base_message.description = "Это хорошее сообщение, но тут есть spam!"
    result = processor.process_update(base_message)
    assert result is None


def test_filter_by_excluded_author(processor, base_message):
    """1 часть TC-2.2 Фильтрация по автору."""
    base_message.author = "bot-user"
    result = processor.process_update(base_message)
    assert result is None


def test_filter_by_min_length(processor, base_message):
    """1 часть TC-2.3 Фильтрация по минимальной длине."""
    base_message.description = "Слишком коротко"
    result = processor.process_update(base_message)
    assert result is None


def test_valid_update_passes_filter(processor, base_message):
    """1 часть TC-2.4 Обновление проходит фильтрацию."""
    result = processor.process_update(base_message)
    assert result is not None
    assert result.id == base_message.id


@patch("src.processor.requests.post")
def test_summarization_long_text(mock_post, processor, base_message):
    """1 часть TC-3.1 Суммаризация длинного текста."""
    long_text = "A" * 100
    base_message.description = long_text

    mock_response = Mock()
    mock_response.json.return_value = {
        "choices": [{"message": "Искусственное сокращение текста"}]
    }
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    result = processor.process_update(base_message)

    assert result is not None
    assert len(result.description) == processor.threshold + 3
    assert result.description.endswith("...")


def test_no_summarization_for_short_text(processor, base_message):
    """1 часть TC-3.2 Короткий текст (суммаризация не выполняется)."""
    short_text = "Это сообщение пройдет без суммаризации"
    base_message.description = short_text

    result = processor.process_update(base_message)

    assert result is not None
    assert result.description == short_text


@patch("src.processor.requests.post")
def test_summarization_fallback_on_api_failure(mock_post, processor, base_message):
    """1 часть TC-3.3 Фоллбек на обрезку при ошибке AI API."""
    long_text = "B" * 100
    base_message.description = long_text

    mock_post.side_effect = Exception("API error")

    result = processor.process_update(base_message)

    assert result is not None
    assert len(result.description) == processor.threshold + 3
    assert result.description.endswith("...")


def test_summarization_fallback_without_token(processor, base_message):
    """1 часть TC-3.4 Фоллбек на обрезку при отсутствии токена."""
    config.hf_api_token = None
    long_text = "C" * 100
    base_message.description = long_text

    result = processor.process_update(base_message)

    assert result is not None
    assert len(result.description) == processor.threshold + 3
    assert result.description.endswith("...")


def test_prioritization_high(processor, base_message):
    """2 часть TC-1.1 Обновление высокой значимости."""
    base_message.description = "This is a critical bug fix!"
    result = processor.process_update(base_message)

    assert result is not None
    assert result.priority == PriorityEnum.HIGH


def test_prioritization_medium(processor, base_message):
    """2 часть TC-1.2 Обновление обычной значимости."""
    base_message.description = "Just a standard update without special words."
    result = processor.process_update(base_message)

    assert result is not None
    assert result.priority == PriorityEnum.MEDIUM


def test_prioritization_low(processor, base_message):
    """2 часть TC-1.3 Обновление низкой значимости."""
    base_message.description = "Fixed a typo in the documentation."
    result = processor.process_update(base_message)

    assert result is not None
    assert result.priority == PriorityEnum.LOW
