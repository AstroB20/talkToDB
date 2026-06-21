#!/bin/sh
set -e

# Start the FastAPI backend on port 8000 (internal only)
uvicorn api.main:app --host 0.0.0.0 --port 8000 &

# Wait until the API is healthy (max 60s) before starting the UI
echo "Waiting for API to start..."
retries=0
until python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" 2>/dev/null; do
  retries=$((retries + 1))
  if [ "$retries" -ge 60 ]; then
    echo "ERROR: API failed to start after 60 seconds. Exiting."
    exit 1
  fi
  sleep 1
done
echo "API is up — starting Streamlit."

# Start Streamlit in the foreground on Cloud Run's $PORT (default 8501 locally)
exec streamlit run ui/app.py \
  --server.port "${PORT:-8501}" \
  --server.address 0.0.0.0
