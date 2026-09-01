from enum import Enum
from pydantic import BaseModel, Field


class PriorityEnum(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RawUpdateMessage(BaseModel):
    id: int
    url: str
    author: str
    description: str
    tgChatIds: list[int]


class ProcessedUpdateMessage(BaseModel):
    id: int
    url: str
    description: str
    tgChatIds: list[int]
    priority: PriorityEnum = Field(default=PriorityEnum.MEDIUM)
