import requests
import structlog
from typing import Any

from src.config import config
from src.models import RawUpdateMessage, ProcessedUpdateMessage, PriorityEnum

logger = structlog.getLogger(__name__)

timeout = config.request_timeout


class UpdateProcessor:
    def __init__(self):
        self.stop_words = {word.lower() for word in config.stop_words}
        self.excluded_authors = {author.lower() for author in config.excluded_authors}
        self.min_length = config.filter_min_length
        self.threshold = config.summarization_threshold

        self.high_keywords = [kw.lower() for kw in config.high_keywords]
        self.low_keywords = [kw.lower() for kw in config.low_keywords]

        self.api_url = config.ai_api_url
        self.headers = {"Authorization": f"Bearer {config.hf_api_token}"}

    def _is_valid(self, message: RawUpdateMessage) -> bool:
        """Проверяет сообщение на соответствие правилам фильтрации."""

        # Проверка исключенных авторов
        if message.author.lower() in self.excluded_authors:
            logger.info(
                "Сообщение отклонено: Автор исключен.",
                stage="filtering",
                message_id=message.id,
                author=message.author,
            )
            return False

        # Проверка минимальной длины
        if len(message.description) < self.min_length:
            logger.info(
                f"Сообщение отклонено: Длина сообщения < {self.min_length}.",
                stage="filtering",
                message_id=message.id,
                message_length=len(message.description),
            )
            return False

        # Проверка стоп-слов
        description_lower = message.description.lower()
        for word in self.stop_words:
            if word in description_lower:
                logger.info(
                    "Сообщение отклонено: Содержит стоп-слово.",
                    stage="filtering",
                    message_id=message.id,
                    stop_word=word,
                )
                return False

        return True

    def _query_ai_api(self, text: str) -> str:
        """Запрос к AI API для суммаризации текста."""
        message = "Суммаризируй следующее сообщение в 1-2 предложениях:\n" + text
        payload: dict[str, Any] = {
            "messages": [{"role": "user", "content": message}],
            "model": "deepseek-ai/DeepSeek-V4-Pro:novita",
        }
        response = requests.post(
            self.api_url, headers=self.headers, json=payload, timeout=timeout
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    def _summarize(self, text: str, message_id: int) -> str:
        """Суммаризация текста через AI API с фолбэком на обрезку."""
        if len(text) <= self.threshold:
            return text

        if not config.hf_api_token:
            logger.warning(
                "Токен HF не задан, используется обрезка текста", message_id=message_id
            )
            return text[: self.threshold] + "..."

        logger.info(
            "Отправка текста в AI API для суммаризации...",
            stage="summarization",
            message_id=message_id,
            text_length=len(text),
        )
        try:
            summary = self._query_ai_api(text)
            logger.info(
                "Суммаризация успешно завершена",
                stage="summarization",
                message_id=message_id,
            )
            return summary

        except requests.exceptions.ReadTimeout:
            logger.error(
                "Таймаут ожидания ответа от AI API",
                stage="summarization",
                message_id=message_id,
            )
        except Exception as e:
            logger.error(
                "Ошибка при обращении к AI API",
                error=str(e),
                stage="summarization",
                message_id=message_id,
            )

        # Фолбэк: если API упало, просто режем текст
        return text[: self.threshold] + "..."

    def _calculate_priority(self, text: str) -> PriorityEnum:
        """Определяет приоритет на основе ключевых слов."""
        text_lower = text.lower()

        if any(keyword in text_lower for keyword in self.high_keywords):
            return PriorityEnum.HIGH

        if any(keyword in text_lower for keyword in self.low_keywords):
            return PriorityEnum.LOW

        return PriorityEnum.MEDIUM

    def process_update(
        self, message: RawUpdateMessage
    ) -> ProcessedUpdateMessage | None:
        """
        Основной пайплайн обработки одного сообщения.
        Возвращает ProcessedUpdateMessage, если сообщение прошло фильтры, иначе None.
        """
        logger.debug(
            "Начало обработки сообщения", stage="processing", message_id=message.id
        )

        if not self._is_valid(message):
            return None

        processed_text = self._summarize(message.description, message.id)

        priority = self._calculate_priority(processed_text)

        processed_message = ProcessedUpdateMessage(
            id=message.id,
            url=message.url,
            description=processed_text,
            tgChatIds=message.tgChatIds,
            priority=priority,
        )

        logger.info(
            "Сообщение успешно обработано.", stage="processing", message_id=message.id
        )
        return processed_message
