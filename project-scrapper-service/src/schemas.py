from datetime import datetime
from enum import Enum
from pydantic import BaseModel, HttpUrl


class UpdateType(str, Enum):
    """Тип обнаруженного изменения."""

    SO_ANSWER = "so_answer"
    SO_COMMENT = "so_comment"

    GITHUB_PR = "github_pr"
    GITHUB_ISSUE = "github_issue"


class LinkUpdateDetails(BaseModel):
    """Внутренняя модель для сбора данных об изменениях."""

    update_type: UpdateType
    title: str
    username: str
    created_at: datetime
    preview: str
    url: str


# --- Request Models ---


class AddLinkRequest(BaseModel):
    link: HttpUrl
    tags: list[str]
    filters: list[str]


class RemoveLinkRequest(BaseModel):
    link: HttpUrl


class LinkUpdateRequest(BaseModel):
    id: int
    author: str
    url: str
    description: str
    tgChatIds: list[int]


# --- Response Models ---


class LinkResponse(BaseModel):
    id: int
    url: HttpUrl
    tags: list[str]
    filters: list[str | None]
    updated_at: datetime | None


class ApiErrorResponse(BaseModel):
    description: str
    code: str
    exceptionName: str
    exceptionMessage: str
    stacktrace: list[str]


class ListLinksResponse(BaseModel):
    links: list[LinkResponse]
    size: int
