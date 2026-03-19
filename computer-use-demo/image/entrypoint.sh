#!/bin/bash
set -e

./start_all.sh
./novnc_startup.sh

python http_server.py > /tmp/server_logs.txt 2>&1 &

if [ "${USE_FASTAPI:-0}" = "1" ]; then
  PORT=8000 python -m computer_use_demo.api > /tmp/api_stdout.log 2>&1 &
  API_PORT="${HOST_API_PORT:-8000}"
  echo "✨ Computer Use Demo (FastAPI) is ready!"
  echo "➡️  API & Frontend: http://localhost:${API_PORT}"
  echo "➡️  Docs: http://localhost:${API_PORT}/docs"
  echo "➡️  VNC (noVNC): http://localhost:6080"
else
  STREAMLIT_SERVER_PORT=8501 python -m streamlit run computer_use_demo/streamlit.py > /tmp/streamlit_stdout.log &
  echo "✨ Computer Use Demo (Streamlit) is ready!"
  echo "➡️  Open http://localhost:8080 in your browser to begin"
fi

# Keep the container running
tail -f /dev/null
