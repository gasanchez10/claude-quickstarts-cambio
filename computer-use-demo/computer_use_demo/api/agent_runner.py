"""Run the computer-use sampling loop with progress streaming and single-writer lock."""

import asyncio
import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, get_args

import httpx
from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaMessageParam,
    BetaTextBlockParam,
    BetaToolResultBlockParam,
)

from computer_use_demo.loop import APIProvider, sampling_loop
from computer_use_demo.tools import ToolResult, ToolVersion

from .session_store import (
    get_messages,
    get_running_session_id,
    get_session,
    persist_messages,
    set_session_status,
)


class AnotherSessionRunningError(Exception):
    """Raised when a run is rejected because another session is already running."""

    def __init__(self, running_session_id: str) -> None:
        self.running_session_id = running_session_id
        super().__init__(f"Another session is running: {running_session_id}")

# Default model per provider (aligned with streamlit.py)
PROVIDER_DEFAULT_MODEL: dict[str, str] = {
    APIProvider.ANTHROPIC: "claude-sonnet-4-5-20250929",
    APIProvider.BEDROCK: "anthropic.claude-3-5-sonnet-20241022-v2:0",
    APIProvider.VERTEX: "claude-3-5-sonnet-v2@20241022",
}


@dataclass
class RunConfig:
    """Config for one agent run."""

    session_id: str
    api_key: str
    provider: str = "anthropic"
    model: str | None = None
    system_prompt_suffix: str = ""
    tool_version: str = "computer_use_20250124"
    max_tokens: int = 16384
    only_n_most_recent_images: int | None = 3
    thinking_budget: int | None = None
    token_efficient_tools_beta: bool = False


# One lock per process: only one sampling_loop runs at a time to avoid VM/display races
_agent_lock = asyncio.Lock()


@dataclass
class StreamQueue:
    """Queue of SSE events for one run."""

    queue: asyncio.Queue[dict[str, Any]] = field(default_factory=asyncio.Queue)
    closed: bool = False
    last_error: str | None = None  # set by api_response_callback when API fails

    def put(self, event: str, data: dict[str, Any] | None = None) -> None:
        if self.closed:
            return
        self.queue.put_nowait({"event": event, "data": data or {}})

    def close(self) -> None:
        self.closed = True
        self.queue.put_nowait({"event": "done", "data": {}})


def _content_to_json(block: BetaContentBlockParam) -> dict[str, Any]:
    """Convert content block to JSON-serializable dict."""
    if isinstance(block, dict):
        return dict(block)
    return block.model_dump() if hasattr(block, "model_dump") else {"type": "unknown"}


def _tool_result_to_json(result: ToolResult, tool_use_id: str) -> dict[str, Any]:
    return {
        "tool_use_id": tool_use_id,
        "output": result.output,
        "error": result.error,
        "has_image": bool(result.base64_image),
    }


async def run_agent(
    config: RunConfig,
    user_message: str,
    stream: StreamQueue,
) -> tuple[list[BetaMessageParam], bool, str | None]:
    """
    Run the sampling loop for the given session and user message.
    Pushes progress to stream. Acquires _agent_lock so only one run is active.
    """
    session = get_session(config.session_id)
    if not session:
        raise ValueError(f"Session not found: {config.session_id}")

    async with _agent_lock:
        running_id = get_running_session_id()
        if running_id is not None and running_id != config.session_id:
            raise AnotherSessionRunningError(running_id)
        set_session_status(config.session_id, "running")
        try:
            messages = get_messages(config.session_id)
            count_before_user = len(messages)
            messages.append({
                "role": "user",
                "content": [BetaTextBlockParam(type="text", text=user_message)],
            })

            try:
                provider = APIProvider(config.provider)
            except ValueError:
                provider = APIProvider.ANTHROPIC
            model = config.model or PROVIDER_DEFAULT_MODEL.get(str(provider), "claude-sonnet-4-5-20250929")
            api_key = config.api_key or os.environ.get("ANTHROPIC_API_KEY", "")

            def output_callback(block: BetaContentBlockParam) -> None:
                stream.put("content", _content_to_json(block))

            def tool_output_callback(result: ToolResult, tool_use_id: str) -> None:
                stream.put("tool_result", _tool_result_to_json(result, tool_use_id))

            def api_response_callback(
                req: httpx.Request,
                resp: httpx.Response | object | None,
                err: Exception | None,
            ) -> None:
                if err is not None:
                    stream.last_error = str(err)
                stream.put(
                    "api_response",
                    {
                        "method": req.method,
                        "url": str(req.url),
                        "error": str(err) if err else None,
                    },
                )

            tool_version = (
                config.tool_version
                if config.tool_version in get_args(ToolVersion)
                else "computer_use_20250124"
            )

            final_messages = await sampling_loop(
                model=model,
                provider=provider,
                system_prompt_suffix=config.system_prompt_suffix,
                messages=messages,
                output_callback=output_callback,
                tool_output_callback=tool_output_callback,
                api_response_callback=api_response_callback,
                api_key=api_key,
                only_n_most_recent_images=config.only_n_most_recent_images,
                max_tokens=config.max_tokens,
                tool_version=tool_version,
                thinking_budget=config.thinking_budget,
                token_efficient_tools_beta=config.token_efficient_tools_beta,
            )

            # Only persist when we got at least one assistant turn (avoid wiping history on API error)
            persisted = len(final_messages) > count_before_user + 1
            if persisted:
                persist_messages(config.session_id, final_messages)
            api_error = stream.last_error if not persisted else None
            return (final_messages, persisted, api_error)
        finally:
            set_session_status(config.session_id, "idle")
            stream.close()


async def run_agent_safe(
    config: RunConfig,
    user_message: str,
    stream: StreamQueue,
) -> tuple[list[BetaMessageParam] | None, str | None, bool, str | None]:
    """
    Run agent and return (messages, None, persisted, api_error) on success or (None, error_message, False, None) on failure.
    persisted is True only when at least one assistant turn was saved.
    api_error is set when the run finished without a model response (e.g. API key or API error).
    """
    try:
        messages, persisted, api_error = await run_agent(config, user_message, stream)
        return (messages, None, persisted, api_error)
    except AnotherSessionRunningError as e:
        return (None, f"Another session is running (id: {e.running_session_id[:8]}...). Only one run at a time.", False, None)
    except Exception as e:
        stream.put("error", {"message": str(e)})
        stream.close()
        return (None, str(e), False, None)
