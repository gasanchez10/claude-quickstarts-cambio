"""SQLite persistence for sessions and chat history."""

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """Declarative base for models."""


class DBSession(Base):
    """One agent session (chat)."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), default="idle")  # idle | running
    config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(True), server_default=func.now(), onupdate=func.now()
    )

    messages_rel: Mapped[list["DBMessage"]] = relationship(
        "DBMessage", back_populates="session", order_by="DBMessage.seq"
    )


class DBMessage(Base):
    """One message in a session (user or assistant turn)."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("sessions.id"), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)  # order within session
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)  # JSON

    session: Mapped["DBSession"] = relationship("DBSession", back_populates="messages_rel")


def _db_path() -> Path:
    path = os.environ.get("COMPUTER_USE_DB_PATH")
    if path:
        return Path(path)
    return Path(__file__).resolve().parents[2] / "data" / "sessions.db"


def get_engine():
    """Create or return engine; ensure DB directory exists and is writable."""
    path = _db_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Fallback to /tmp if default path not writable (e.g. Docker volume permissions)
        path = Path("/tmp/computer_use_demo_sessions.db")
    return create_engine(f"sqlite:///{path}", echo=os.environ.get("SQL_ECHO", "").lower() == "1")


_engine = None


def engine():
    global _engine
    if _engine is None:
        _engine = get_engine()
        try:
            Base.metadata.create_all(_engine)
        except OperationalError:
            # e.g. permission denied on Docker volume; fallback to /tmp
            fallback = create_engine(
                "sqlite:////tmp/computer_use_demo_sessions.db",
                echo=os.environ.get("SQL_ECHO", "").lower() == "1",
            )
            Base.metadata.create_all(fallback)
            _engine = fallback
    return _engine


@contextmanager
def session_scope() -> Iterator[Session]:
    """Provide a transactional scope for the session."""
    sess = Session(engine())
    try:
        yield sess
        sess.commit()
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()


def _content_block_to_dict(block: Any) -> dict[str, Any]:
    """Convert a single content block (Pydantic or dict) to a JSON-serializable dict."""
    if isinstance(block, dict):
        return dict(block)
    if hasattr(block, "model_dump"):
        return block.model_dump()
    return {"type": "unknown", "raw": str(block)}


def serialize_content(content: list[dict[str, Any]] | str | list[Any]) -> str:
    """Serialize message content for DB. Accepts list of dicts or Pydantic blocks."""
    if isinstance(content, str):
        return json.dumps([{"type": "text", "text": content}])
    if isinstance(content, list):
        normalized = [_content_block_to_dict(b) for b in content]
        return json.dumps(normalized)
    return json.dumps([{"type": "text", "text": str(content)}])


def deserialize_content(raw: str) -> list[dict[str, Any]]:
    """Deserialize message content from DB."""
    return json.loads(raw)
