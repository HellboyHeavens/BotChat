import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ConversationCreate(BaseModel):
    title: str = "Новый диалог"
    system_prompt: str | None = None


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    system_prompt: str | None
    created_at: datetime


class MessageCreate(BaseModel):
    content: str


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    tokens_in: int | None
    tokens_out: int | None
    created_at: datetime


class ChatReply(BaseModel):
    reply: str
    tokens_in: int | None
    tokens_out: int | None

class ConversationDetail(ConversationOut):
    messages: list[MessageOut]

class UsageOut(BaseModel):
    messages_count: int
    tokens_in: int
    tokens_out: int
    tokens_total: int
