# Anthropic Computer Use Demo

> [!NOTE]
> Supports Claude 4 models (e.g. Claude Opus 4.5, Claude Sonnet 4.5). The reference uses `str_replace_based_edit_tool`; see [API release notes](https://docs.claude.com/en/release-notes/api) for the latest.

> [!CAUTION]
> Computer use is a beta feature with distinct risks (e.g. prompt injection, following webpage instructions). Use a dedicated VM/container, avoid sensitive data, limit internet access, and obtain user consent. See [Anthropic documentation](https://docs.anthropic.com) for full guidance.

This repo provides:

- **FastAPI backend** (default): session API, SQLite chat history, one run at a time, no race conditions. Served with a simple HTML/JS frontend. See [REQUIREMENTS_VALIDATION.md](REQUIREMENTS_VALIDATION.md) for a full check against the design requirements.
- **Streamlit app** (legacy): set `USE_FASTAPI=0` to use the Streamlit UI instead.
- **Docker** image and Compose file for running the agent and desktop (Xvfb, noVNC) in a container.
- **Computer use agent loop** and tools (Claude API, Bedrock, or Vertex).

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
| **Chat** | `GET /sessions/{id}/messages` history. `POST /sessions/{id}/run-wait` body `{"content": "..."}` — runs agent, returns when done (default in UI). `POST /sessions/{id}/run` — SSE stream (use run-wait if SSE is buffered). |
| **VNC** | `GET /vnc` noVNC URL |
| **Health** | `GET /health` |

**Concurrency:** Create, list, get, delete sessions and get messages can run concurrently. Only one agent run is allowed at a time (single shared desktop); a second run returns **409** with a message that another session is running. No simultaneous runs; no race on desktop or chat state.

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
