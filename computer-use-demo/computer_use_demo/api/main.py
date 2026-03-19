"""
FastAPI backend for computer use agent: session management, SSE progress, VNC info.
"""

import asyncio
import json
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from sse_starlette.sse import EventSourceResponse

from computer_use_demo.loop import APIProvider

from .agent_runner import RunConfig, StreamQueue, run_agent_safe
from .database import engine
from .schemas import MessageSend, RunWaitResponse, SessionCreate, SessionResponse, VncInfo
from .session_store import (
    create_session,
    delete_session,
    get_messages,
    get_running_session_id,
    get_session,
    list_sessions,
)

app = FastAPI(
    title="Computer Use Agent API",
    description="Session management, SSE progress streaming, and VNC info for the computer use demo. "
    "Sessions and chat history are persisted in SQLite; only one agent run at a time (409 when busy).",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _vnc_base_url(request: Request) -> str:
    """Base URL for noVNC; same host as request, port 6080."""
    base = os.environ.get("VNC_WEB_URL", "").strip()
    if base:
        return base.rstrip("/")
    from urllib.parse import urlparse
    u = urlparse(str(request.base_url))
    host = u.hostname or "localhost"
    return f"{u.scheme}://{host}:6080"


# ----- Sessions -----


@app.post("/sessions", response_model=SessionResponse, tags=["Sessions"])
def api_create_session(body: SessionCreate) -> SessionResponse:
    """Create a new agent session with optional config."""
    config: dict[str, Any] = {
        "provider": body.provider,
        "model": body.model,
        "system_prompt_suffix": body.system_prompt_suffix,
        "tool_version": body.tool_version,
        "max_tokens": body.max_tokens,
        "only_n_most_recent_images": body.only_n_most_recent_images,
        "thinking_budget": body.thinking_budget,
        "token_efficient_tools_beta": body.token_efficient_tools_beta,
    }
    if body.api_key is not None:
        config["api_key"] = body.api_key
    sid = create_session(config)
    sess = get_session(sid)
    assert sess is not None
    return SessionResponse(
        id=sess["id"],
        status=sess["status"],
        created_at=sess["created_at"],
        updated_at=sess["updated_at"],
        message_count=0,
    )


@app.get("/sessions", response_model=list[SessionResponse], tags=["Sessions"])
def api_list_sessions() -> list[SessionResponse]:
    """List all sessions."""
    return [
        SessionResponse(
            id=s["id"],
            status=s["status"],
            created_at=s["created_at"],
            updated_at=s["updated_at"],
            message_count=s["message_count"],
        )
        for s in list_sessions()
    ]


@app.get("/sessions/{session_id}", response_model=SessionResponse, tags=["Sessions"])
def api_get_session(session_id: str) -> SessionResponse:
    """Get one session by id."""
    sess = get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionResponse(
        id=sess["id"],
        status=sess["status"],
        created_at=sess["created_at"],
        updated_at=sess["updated_at"],
        message_count=len(get_messages(session_id)),
    )


@app.delete("/sessions/{session_id}", status_code=204, tags=["Sessions"])
def api_delete_session(session_id: str) -> None:
    """Delete a session and its chat history."""
    if not delete_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")


# ----- Messages (chat history) -----


@app.get("/sessions/{session_id}/messages", tags=["Chat"])
def api_get_messages(session_id: str) -> list[dict[str, Any]]:
    """Get full message list for a session (for display)."""
    if get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = get_messages(session_id)
    return [
        {
            "role": m["role"],
            "content": m["content"],
        }
        for m in messages
    ]


def _run_config(session_id: str) -> tuple[dict[str, Any], RunConfig]:
    """Validate session and build RunConfig; raise HTTPException on error."""
    sess = get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    running_id = get_running_session_id()
    if running_id is not None:
        if running_id == session_id:
            raise HTTPException(
                status_code=409,
                detail="This session already has a run in progress.",
            )
        raise HTTPException(
            status_code=409,
            detail=f"Another session is running (id: {running_id[:8]}...). Only one run at a time; wait for it to finish or switch to that session.",
        )
    cfg = sess["config"]
    api_key = cfg.get("api_key") or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key and str(cfg.get("provider", "anthropic")) == APIProvider.ANTHROPIC:
        raise HTTPException(
            status_code=400,
            detail="API key required. Set ANTHROPIC_API_KEY when starting the container (e.g. ANTHROPIC_API_KEY=sk-... docker compose up).",
        )
    config = RunConfig(
        session_id=session_id,
        api_key=api_key,
        provider=str(cfg.get("provider", "anthropic")),
        model=cfg.get("model"),
        system_prompt_suffix=str(cfg.get("system_prompt_suffix", "")),
        tool_version=str(cfg.get("tool_version", "computer_use_20250124")),
        max_tokens=cfg.get("max_tokens", 16384),
        only_n_most_recent_images=cfg.get("only_n_most_recent_images", 3),
        thinking_budget=cfg.get("thinking_budget"),
        token_efficient_tools_beta=bool(cfg.get("token_efficient_tools_beta", False)),
    )
    return (sess, config)


@app.post(
    "/sessions/{session_id}/run-wait",
    response_model=RunWaitResponse,
    tags=["Chat"],
    summary="Run agent (blocking)",
)
async def api_run_session_wait(session_id: str, body: MessageSend) -> RunWaitResponse:
    """
    Run the agent and wait for completion (no streaming). Use this if the
    streaming **run** endpoint never delivers events in your environment.
    May take 1–3 minutes. Returns when the run finishes or fails.
    """
    _, config = _run_config(session_id)
    stream = StreamQueue()
    messages, err, persisted, api_error = await run_agent_safe(config, body.content, stream)
    if err:
        if "Another session is running" in err:
            raise HTTPException(status_code=409, detail=err)
        raise HTTPException(status_code=500, detail=err)
    return RunWaitResponse(
        status="ok",
        message_count=len(messages) if messages else 0,
        persisted=persisted,
        error=api_error,
    )


@app.post(
    "/sessions/{session_id}/run",
    tags=["Chat"],
    summary="Run agent (SSE stream)",
)
def api_run_session(
    session_id: str,
    body: MessageSend,
    request: Request,
):
    """
    Send a user message and run the agent. Returns an **SSE** stream of progress events.

    **Events:** `started`, `content` (text/thinking/tool_use), `tool_result`, `api_response`, `error`, `ping` (keepalive), `done`.

    If the client never receives events (e.g. buffered proxy), use **run-wait** instead.
    """
    _, config = _run_config(session_id)
    stream = StreamQueue()

    async def event_generator():
        # Send a larger first chunk to force flush (some proxies buffer until ~1KB)
        yield {"event": "started", "data": json.dumps({"status": "started"}) + " " * 1024}
        task = asyncio.create_task(
            run_agent_safe(config, body.content, stream),
        )
        sent_done = False
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(stream.queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": {}}
                    continue
                if msg["event"] == "done":
                    sent_done = True
                    yield {
                        "event": "done",
                        "data": json.dumps(msg["data"]) if isinstance(msg["data"], dict) else msg["data"],
                    }
                    break
                yield {
                    "event": msg["event"],
                    "data": json.dumps(msg["data"]) if isinstance(msg["data"], dict) else msg["data"],
                }
            await task
        finally:
            if not sent_done:
                yield {"event": "done", "data": "{}"}

    return EventSourceResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ----- VNC -----


@app.get("/vnc", response_model=VncInfo, tags=["VNC"])
def api_vnc_info(request: Request) -> VncInfo:
    """Return the noVNC URL for connecting to the virtual machine."""
    base = _vnc_base_url(request)
    return VncInfo(
        vnc_web_url=f"{base}/vnc.html?resize=scale&autoconnect=1&view_only=1&reconnect=1&reconnect_delay=2000",
        view_only_param="1",
    )


# ----- Health -----


@app.get("/health", tags=["Health"])
def health() -> dict[str, str]:
    """Health check for deployments."""
    return {"status": "ok"}


# ----- Serve frontend (optional) -----


@app.get("/", response_class=HTMLResponse)
def serve_frontend() -> HTMLResponse:
    """Serve the demo frontend if index exists."""
    path = os.environ.get("COMPUTER_USE_FRONTEND", "")
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    # Minimal fallback
    return HTMLResponse(
        content="""<!DOCTYPE html><html><head><title>Computer Use API</title></head><body>
        <h1>Computer Use Agent API</h1>
        <p><a href="/docs">OpenAPI docs</a></p>
        <p><a href="/vnc">VNC info</a></p>
        <p>POST /sessions to create a session, then POST /sessions/{id}/run-wait with {"content": "..."} (or /run for SSE).</p>
        </body></html>"""
    )


def init_db() -> None:
    """Ensure DB tables exist."""
    engine()


@app.on_event("startup")
def on_startup() -> None:
    init_db()
