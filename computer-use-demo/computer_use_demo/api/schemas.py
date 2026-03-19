"""Pydantic schemas for session management API."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    """Request body for creating a session."""

    api_key: str | None = Field(None, description="Anthropic API key (optional if set via env)")
    provider: str = Field(default="anthropic", description="API provider: anthropic, bedrock, vertex")
    model: str | None = Field(
        default=None,
        description="Model name; default per provider if omitted",
    )
    system_prompt_suffix: str = Field(default="", description="Extra system prompt suffix")
    tool_version: str = Field(
        default="computer_use_20250124",
        description="Tool version",
    )
    max_tokens: int = Field(default=16384, ge=1, le=128_000)
    only_n_most_recent_images: int | None = Field(
        default=3,
        ge=0,
        description="Limit images in context; null = no limit",
    )
    thinking_budget: int | None = Field(default=None, ge=0)
    token_efficient_tools_beta: bool = Field(default=False)


class SessionResponse(BaseModel):
    """Session summary for list/get."""

    id: str
    status: str  # idle | running
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class MessageSend(BaseModel):
    """Request body for sending a user message and running the agent."""

    content: str = Field(..., min_length=1)


class VncInfo(BaseModel):
    """VNC / noVNC connection info."""

    vnc_web_url: str = Field(..., description="URL to open noVNC in browser")
    view_only_param: str = Field(default="1", description="view_only=1 or 0")
