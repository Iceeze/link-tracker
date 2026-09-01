class ApiException(Exception):
    """Базовый класс для всех кастомных исключений API."""

    def __init__(
        self,
        description: str,
        code: str,
        status_code: int = 500,
    ):
        self.description = description
        self.code = code
        self.status_code = status_code
        super().__init__(self.description)


class ChatNotFoundException(ApiException):
    """Чат не найден в базе данных."""

    def __init__(self, chat_id: int):
        super().__init__(
            description=f"Chat with id={chat_id} not found",
            code="404",
            status_code=404,
        )
        self.chat_id = chat_id


class ChatAlreadyExistsException(ApiException):
    """Чат уже зарегистрирован в системе."""

    def __init__(self, chat_id: int):
        super().__init__(
            description=f"Chat with id={chat_id} already exists",
            code="409",
            status_code=409,
        )
        self.chat_id = chat_id


class LinkNotFoundException(ApiException):
    """Ссылка не найдена в базе данных."""

    def __init__(self, url: str):
        super().__init__(
            description=f"Link with url={url} not found",
            code="404",
            status_code=404,
        )
        self.url = url


class LinkAlreadyExistsException(ApiException):
    """Ссылка уже отслеживается для данного чата."""

    def __init__(self, url: str):
        super().__init__(
            description=f"Link with url={url} already exists",
            code="409",
            status_code=409,
        )
        self.url = url


class DatabaseException(ApiException):
    """Ошибка работы с базой данных."""

    def __init__(self, message: str = "Database error occurred"):
        super().__init__(
            description=message,
            code="500",
            status_code=500,
        )
