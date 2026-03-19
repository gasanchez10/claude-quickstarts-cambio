#!/bin/bash
set -e

# Start X11, VNC, noVNC (same as original)
./start_all.sh
./novnc_startup.sh

# Optional: static file server for assets (e.g. port 8080)
python http_server.py > /tmp/server_logs.txt 2>&1 &

# FastAPI backend (session API + optional frontend at /)
PORT=8000 python -m computer_use_demo.api > /tmp/api_stdout.log 2>&1 &

echo "✨ Computer Use Demo (FastAPI) is ready!"
echo "➡️  API: http://localhost:8000"
echo "➡️  Docs: http://localhost:8000/docs"
echo "➡️  Frontend: http://localhost:8000/"
echo "➡️  VNC (noVNC): http://localhost:6080"

# Keep the container running
tail -f /dev/null
