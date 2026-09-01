from datetime import datetime
from enum import Enum
from pydantic import BaseModel, HttpUrl, Field


class PriorityEnum(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class LinkUpdate(BaseModel):
    id: int
    url: str
    description: str
    tgChatIds: list[int]
    priority: PriorityEnum = Field(default=PriorityEnum.MEDIUM)


class LinkResponse(BaseModel):
    id: int
    url: HttpUrl
    tags: list[str]
    filters: list[str | None]
    updated_at: datetime | None


class ListLinksResponse(BaseModel):
    links: list[LinkResponse]
    size: int


class ApiErrorResponse(BaseModel):
    description: str
    code: str
    exceptionName: str
    exceptionMessage: str
    stacktrace: list[str]
