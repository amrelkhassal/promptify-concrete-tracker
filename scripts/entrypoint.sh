#!/usr/bin/env bash
set -euo pipefail

echo "[entrypoint] Applying database migrations..."
alembic upgrade head

echo "[entrypoint] Starting Streamlit on :8501..."
exec streamlit run app/main.py \
    --server.port=8501 \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.fileWatcherType=none
