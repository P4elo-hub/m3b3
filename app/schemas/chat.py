"""Pydantic-схемы для LLM API."""

from pydantic import BaseModel, Field


class StreamChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="Текст запроса пользователя")
    model: str | None = Field(default=None, description="Переопределение модели (опционально)")
