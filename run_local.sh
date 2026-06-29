#!/usr/bin/env bash
# One-command local run: seed demo data (if DB empty), start the API, then the dashboard.
# Usage:  bash run_local.sh          # uses synthetic demo data
#         INGEST=1 bash run_local.sh # pulls live data from yfinance instead
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Ensuring tables exist"
python -c "from backend.database import init_db; init_db()"

if [ "${INGEST:-0}" = "1" ]; then
  echo "==> Ingesting LIVE data from yfinance"
  python -m backend.ingest
else
  echo "==> Seeding synthetic demo data"
  python -m scripts.seed_demo
fi

echo "==> Starting API on http://127.0.0.1:8000  (docs at /docs)"
uvicorn backend.main:app --host 127.0.0.1 --port 8000 &
API_PID=$!
trap 'kill $API_PID 2>/dev/null || true' EXIT
sleep 4

echo "==> Starting dashboard on http://localhost:8501"
export FINPULSE_API_URL="http://127.0.0.1:8000"
streamlit run dashboard/app.py
