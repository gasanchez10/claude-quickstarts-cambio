"""End-to-end API tests. Run with: pytest tests/test_api_e2e.py -v
   Against container: BASE_URL=http://localhost:8888 pytest tests/test_api_e2e.py -v
"""

import os
import time

import pytest
import requests

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8000")


@pytest.fixture(scope="module")
def session_id():
    r = requests.post(
        f"{BASE}/sessions",
        json={"provider": "anthropic", "max_tokens": 16384, "only_n_most_recent_images": 3},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "id" in data
    return data["id"]


def test_health():
    r = requests.get(f"{BASE}/health", timeout=5)
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_create_session():
    r = requests.post(
        f"{BASE}/sessions",
        json={"provider": "anthropic", "max_tokens": 16384},
        timeout=10,
    )
    assert r.status_code == 200
    data = r.json()
    assert "id" in data
    assert data["status"] == "idle"
    assert data["message_count"] == 0


def test_list_sessions():
    r = requests.get(f"{BASE}/sessions", timeout=5)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)


def test_get_session(session_id):
    r = requests.get(f"{BASE}/sessions/{session_id}", timeout=5)
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == session_id


def test_get_messages_empty(session_id):
    r = requests.get(f"{BASE}/sessions/{session_id}/messages", timeout=5)
    assert r.status_code == 200
    assert r.json() == []


def test_vnc_info():
    r = requests.get(f"{BASE}/vnc", timeout=5)
    assert r.status_code == 200
    data = r.json()
    assert "vnc_web_url" in data
    assert "6080" in data["vnc_web_url"]


def test_frontend_served():
    r = requests.get(f"{BASE}/", timeout=5)
    assert r.status_code == 200
    assert "Computer Use Agent" in r.text or "Computer Use API" in r.text


def test_run_returns_sse_stream(session_id):
    r = requests.post(
        f"{BASE}/sessions/{session_id}/run",
        json={"content": "Reply with exactly: OK"},
        headers={"Accept": "text/event-stream"},
        stream=True,
        timeout=90,
    )
    assert r.status_code == 200
    assert "text/event-stream" in r.headers.get("Content-Type", "")
    # Consume stream for up to 25s, collect event types
    start = time.time()
    event_types = []
    for line in r.iter_lines(decode_unicode=True):
        if time.time() - start > 25:
            break
        if line and line.startswith("event:"):
            event_types.append(line.split(":", 1)[1].strip())
        if "done" in event_types or "error" in event_types:
            break
    r.close()
    # Stream accepted; we may get ping, content, tool_result, done, etc.
    assert r.status_code == 200
