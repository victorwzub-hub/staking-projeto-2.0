from __future__ import annotations

from pydantic import BaseModel, Field


class MessageResponse(BaseModel):
    message: str


class Page[T](BaseModel):
    items: list[T]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class CursorPage[T](BaseModel):
    items: list[T]
    next_cursor: str | None = None
    limit: int = Field(ge=1, le=100)
