"""Pydantic request / response models for the chat API."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4096, description="User message text.")
    session_id: str | None = Field(
        None,
        min_length=1,
        max_length=64,
        description="Session UUID returned by a previous call. Omit to start a new session.",
    )
    use_rag: bool = Field(True, description="Whether to retrieve RAG context for this turn.")

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("message must not be blank")
        return v


class ChatResponse(BaseModel):
    reply: str = Field(..., description="Bot response text.")
    session_id: str = Field(..., description="Session ID to pass on the next request.")


class ClearResponse(BaseModel):
    session_id: str
    cleared: bool = True


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
