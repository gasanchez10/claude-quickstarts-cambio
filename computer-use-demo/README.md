# Anthropic Computer Use Demo

> [!NOTE]
> Supports Claude 4 models (e.g. Claude Opus 4.5, Claude Sonnet 4.5). The reference uses `str_replace_based_edit_tool`; see [API release notes](https://docs.claude.com/en/release-notes/api) for the latest.

> [!CAUTION]
> Computer use is a beta feature with distinct risks (e.g. prompt injection, following webpage instructions). Use a dedicated VM/container, avoid sensitive data, limit internet access, and obtain user consent. See [Anthropic documentation](https://docs.anthropic.com) for full guidance.

This repo provides:

- **FastAPI backend** (default): session API, SQLite chat history, SSE progress streaming, one run at a time, no race conditions. Served with a simple HTML/JS frontend. See [REQUIREMENTS_VALIDATION.md](REQUIREMENTS_VALIDATION.md) and [EVALUATION.md](EVALUATION.md) for requirements check and grading.
- **Streamlit app** (legacy): set `USE_FASTAPI=0` to use the Streamlit UI instead.
- **Docker** image and Compose file for running the agent and desktop (Xvfb, noVNC) in a container.
- **Computer use agent loop** and tools (Claude API, Bedrock, or Vertex), reusing the [Anthropic computer-use-demo stack](https://github.com/anthropics/anthropic-quickstarts/tree/main/computer-use-demo).

---

## Demo video

Walkthrough of the FastAPI + frontend + VNC flow: **[Demo recording (Google Drive)](https://drive.google.com/file/d/101GZ0QyjL5PQnEOP_Fhv5Zrit8iBN5xw/view?usp=sharing)**

---

## Solution architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Browser (HTML/JS demo)                                                  │
│  Sessions · Chat · Run (run-wait) · VNC iframe / new tab                 │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ HTTP (REST + optional SSE)
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  FastAPI (computer_use_demo.api)                                         │
│  • Sessions CRUD → session_store + SQLite                                │
│  • GET /messages, POST /run-wait, POST /run (SSE)                        │
│  • GET /vnc → noVNC URL                                                  │
│  • 409 if another session is already running                             │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
         ┌──────────────────────┼──────────────────────┐
         ▼                      ▼                      ▼
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────────────────┐
│ SQLite          │   │ agent_runner    │   │ Xvfb + mutter + x11vnc      │
│ sessions,       │   │ _agent_lock     │   │ + noVNC :6080               │
│ messages        │   │ sampling_loop   │   │ (single shared desktop)     │
└─────────────────┘   └────────┬────────┘   └─────────────────────────────┘
                             │
                             ▼
                    computer_use_demo.loop
                    computer_use_demo.tools
                    (same stack as upstream demo)
```

| Layer | Role |
|-------|------|
| **Frontend** | Calls REST APIs; uses `run-wait` by default; shows VNC in iframe; avoids duplicate session rows (request generation + dedupe); refreshes VNC after runs and when returning to a backgrounded tab. |
| **FastAPI** | Validates sessions, enforces one run at a time (DB `running` + lock), persists chat after successful model turns. |
| **SQLite** | Durable `sessions` and `messages` tables; optional `COMPUTER_USE_DB_PATH`. |
| **Agent** | Wraps upstream `sampling_loop` with progress callbacks → SSE queue or ignored for run-wait. |
| **Desktop** | One VM display per container; all sessions share it; VNC is best-effort in background browser tabs (reload on focus / after run). |

---

## Design requirements (how we address each)

**Goal:** *Design a scalable backend for computer use agent session management* (building on the [Anthropic computer-use-demo](https://github.com/anthropics/anthropic-quickstarts/tree/main/computer-use-demo)).

| # | Requirement | How we address it |
|---|-------------|-------------------|
| **1** | **Reuse the existing computer use agent stack** | Same `Dockerfile` / desktop startup, `computer_use_demo.loop.sampling_loop`, `computer_use_demo.tools`, providers (Anthropic / Bedrock / Vertex). FastAPI is a new control plane, not a rewrite of the agent. |
| **2a** | **Session creation and management APIs** | `POST /sessions`, `GET /sessions`, `GET /sessions/{id}`, `DELETE /sessions/{id}` with Pydantic models and OpenAPI tags. |
| **2b** | **Real-time progress (WebSocket, SSE, or choice)** | **SSE:** `POST /sessions/{id}/run` (`EventSourceResponse`) with `started`, `content`, `tool_result`, `api_response`, `error`, `ping`, `done`. **Blocking alternative:** `POST /sessions/{id}/run-wait` returns JSON when the run finishes (default in the UI when proxies buffer SSE). |
| **2c** | **VNC connection to virtual machine** | Container runs Xvfb, mutter, x11vnc, noVNC on port **6080**. `GET /vnc` returns the noVNC URL; the demo page embeds it and links “Open in new tab”. |
| **2d** | **Database persistence for chat history** | SQLite via SQLAlchemy (`DBSession`, `DBMessage`); full conversation persisted after a successful assistant turn; `GET /sessions/{id}/messages`. |
| **2e** | **Concurrent session requests without race conditions** | Create/list/get/delete/messages are concurrent and isolated per DB transaction. Only one **run** at a time: global `asyncio.Lock` + `sessions.status = running` + **409** for a second run. Frontend ignores stale `loadChat` / `loadSessions` responses and dedupes session ids. |
| **3** | **Docker for local dev and deployment** | `docker-compose.yml` (API on host **8888**, VNC **6080**), env for API key and DB path; same image works for remote deploy. |
| **4** | **Simple HTML/JS frontend** | Single `frontend/index.html`: session list, chat, Run, VNC panel, progress log, API base URL. |

---

## Quickstart (Docker Compose)

**Requires:** [Anthropic API key](https://console.anthropic.com/) and Docker.

```bash
cd computer-use-demo
ANTHROPIC_API_KEY=sk-ant-api03-... docker compose up
```

- **Frontend & API:** http://localhost:8888  
- **API docs:** http://localhost:8888/docs  
- **VNC (desktop):** http://localhost:6080  

Create a session, type a message, click **Run**. The agent runs on the shared desktop; only one run at a time (a second run returns 409). Chat history is per session and persisted in SQLite.

**UX note:** If the VNC iframe looks frozen after you switch to another browser tab for a while, use **Reload VNC** or open VNC in a new tab—browsers throttle background tabs.

---

## Running with plain Docker

### Claude API

```bash
export ANTHROPIC_API_KEY=sk-ant-api03-...
docker run \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  -v $HOME/.anthropic:/home/computeruse/.anthropic \
  -p 8000:8000 -p 6080:6080 -p 8501:8501 -p 8080:8080 \
  -it ghcr.io/anthropics/anthropic-quickstarts:computer-use-demo-latest
```

- **FastAPI:** http://localhost:8000  
- **VNC:** http://localhost:6080/vnc.html  

### Bedrock / Vertex

Use the same ports; set `API_PROVIDER=bedrock` or `API_PROVIDER=vertex` and pass the required credentials (e.g. AWS profile, Vertex project). See the [original quickstart](https://github.com/anthropics/anthropic-quickstarts/tree/main/computer-use-demo) for full Bedrock/Vertex examples.

---

## API reference (FastAPI)

| Area | Endpoints |
|------|-----------|
| **Sessions** | `POST /sessions` create, `GET /sessions` list, `GET /sessions/{id}` get, `DELETE /sessions/{id}` delete |
| **Chat** | `GET /sessions/{id}/messages` history. `POST /sessions/{id}/run-wait` body `{"content": "..."}` — runs agent, returns JSON when done (default in UI). `POST /sessions/{id}/run` — **SSE stream** (events below). Use run-wait if SSE is buffered. |
| **VNC** | `GET /vnc` noVNC URL |
| **Health** | `GET /health` |

**SSE events** (`POST /sessions/{id}/run`): `started` → `content` (text/thinking/tool_use), `tool_result`, `api_response` → `error` (on failure) or `done`. Optional `ping` every 30s if no activity. See `/docs` for full schema.

**Concurrency:** Create, list, get, delete sessions and get messages can run concurrently. Only one agent run is allowed at a time (single shared desktop); a second run returns **409**. No race on desktop or chat state.

**API key:** Set `ANTHROPIC_API_KEY` when starting the container (e.g. `ANTHROPIC_API_KEY=sk-... docker compose up`). Required for the Run button; can also be set per session in create body.

**Data:** Chat stored in SQLite; path defaults to `computer_use_demo/data/sessions.db`, overridable with `COMPUTER_USE_DB_PATH`.

---

## Development

```bash
./setup.sh
docker build . -t computer-use-demo:local
ANTHROPIC_API_KEY=sk-... docker compose up
```

Or run the API only (desktop/VNC must be available elsewhere, e.g. Docker):

```bash
export ANTHROPIC_API_KEY=your_key
python -m computer_use_demo.api
```

---

## Screen size

Set `WIDTH` and `HEIGHT` (e.g. `WIDTH=1920 HEIGHT=1080`) when running the container. For best model accuracy, use XGA (1024×768) or scale images in your tools; see the `computer` tool implementation.

---

## Feedback

[Share feedback](https://forms.gle/BT1hpBrqDPDUrCqo7) on the model, API, or docs.
