"""Session and message CRUD with database persistence."""

import uuid
from typing import Any

from anthropic.types.beta import BetaMessageParam

from .database import (
    DBMessage,
    DBSession,
    deserialize_content,
    engine,
    session_scope,
    serialize_content,
)


def create_session(config: dict[str, Any] | None = None) -> str:
    """Create a new session; returns session id."""
    sid = str(uuid.uuid4())
    with session_scope() as db:
        db.add(DBSession(id=sid, config=config or {}))
    return sid


def get_session(session_id: str) -> dict[str, Any] | None:
    """Load session by id; returns dict or None (safe after scope close)."""
    with session_scope() as db:
        s = db.get(DBSession, session_id)
        if not s:
            return None
        return {
            "id": s.id,
            "status": s.status,
            "config": s.config or {},
            "created_at": s.created_at,
            "updated_at": s.updated_at,
        }


def list_sessions() -> list[dict[str, Any]]:
    """List all sessions with message count."""
    with session_scope() as db:
        rows = db.query(DBSession).order_by(DBSession.updated_at.desc()).all()
        out = []
        for s in rows:
            count = db.query(DBMessage).filter(DBMessage.session_id == s.id).count()
            out.append({
                "id": s.id,
                "status": s.status,
                "created_at": s.created_at,
                "updated_at": s.updated_at,
                "message_count": count,
            })
        return out


def set_session_status(session_id: str, status: str) -> None:
    """Set session status (idle | running)."""
    with session_scope() as db:
        s = db.get(DBSession, session_id)
        if s:
            s.status = status


def get_running_session_id() -> str | None:
    """Return the id of the session that is currently running, or None."""
    with session_scope() as db:
        row = (
            db.query(DBSession.id)
            .filter(DBSession.status == "running")
            .limit(1)
            .first()
        )
        return row[0] if row else None


def get_messages(session_id: str) -> list[BetaMessageParam]:
    """Load full message list for API (BetaMessageParam)."""
    with session_scope() as db:
        msgs = (
            db.query(DBMessage)
            .filter(DBMessage.session_id == session_id)
            .order_by(DBMessage.seq)
            .all()
        )
        return [
            {"role": m.role, "content": deserialize_content(m.content)}
            for m in msgs
        ]


def persist_messages(session_id: str, messages: list[BetaMessageParam]) -> None:
    """
    Replace all messages for a session with the given list.
    Used after the agent run to persist the full updated conversation.
    Content blocks (e.g. from API) are normalized to JSON-serializable dicts.
    """
    with session_scope() as db:
        db.query(DBMessage).filter(DBMessage.session_id == session_id).delete()
        for i, msg in enumerate(messages):
            content = msg.get("content")
            content_json = serialize_content(content if content is not None else "")
            db.add(
                DBMessage(
                    session_id=session_id,
                    seq=i,
                    role=msg.get("role", "user"),
                    content=content_json,
                )
            )


def delete_session(session_id: str) -> bool:
    """Delete session and all messages. Returns True if deleted."""
    with session_scope() as db:
        s = db.get(DBSession, session_id)
        if not s:
            return False
        db.query(DBMessage).filter(DBMessage.session_id == session_id).delete()
        db.delete(s)
        return True
