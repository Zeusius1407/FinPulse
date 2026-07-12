#!/usr/bin/env bash
# Populate the configured database (Supabase/Postgres in prod) with data.
#
# Loads DATABASE_URL from .env if present, runs the live yfinance ingest, and
# automatically falls back to synthetic demo data if the ingest leaves the DB
# empty (e.g. yfinance rate-limited the request).
#
# Usage:
#   bash scripts/populate_supabase.sh                    # uses DATABASE_URL from env/.env
#   DATABASE_URL="postgresql://...supabase..." bash scripts/populate_supabase.sh
#   SEED_ONLY=1 bash scripts/populate_supabase.sh        # skip ingest, seed synthetic data
set -euo pipefail
cd "$(dirname "$0")/.."

# 1) Load .env (KEY=VALUE lines) if the caller didn't already export DATABASE_URL.
if [ -z "${DATABASE_URL:-}" ] && [ -f .env ]; then
  echo "==> Loading DATABASE_URL from .env"
  set -a; . ./.env; set +a
fi

if [ -z "${DATABASE_URL:-}" ]; then
  echo "ERROR: DATABASE_URL is not set. Point it at your Supabase Session-pooler URL," >&2
  echo "       e.g. export DATABASE_URL='postgresql://postgres.REF:PW@aws-0-REGION.pooler.supabase.com:5432/postgres'" >&2
  exit 1
fi

# Redact credentials when echoing which target we're about to write to.
_target="$(printf '%s' "$DATABASE_URL" | sed -E 's#(://[^:]+):[^@]+@#\1:****@#')"
echo "==> Target database: ${_target}"
case "$DATABASE_URL" in
  *localhost*|*127.0.0.1*)
    echo "    (note: this points at a LOCAL database, not Supabase)";;
esac

# Count rows in the quotes table (0 if the table doesn't exist yet).
_quote_count() {
  python - <<'PY'
from sqlalchemy import inspect, text
from backend.database import engine
try:
    if not inspect(engine).has_table("quotes"):
        print(0)
    else:
        with engine.connect() as c:
            print(c.execute(text("SELECT count(*) FROM quotes")).scalar() or 0)
except Exception:
    print(0)
PY
}

# 2) SEED_ONLY forces synthetic data (re-seeding is idempotent). Otherwise run
#    the live ingest and fall back to seeding only if it leaves the DB empty.
if [ "${SEED_ONLY:-0}" = "1" ]; then
  echo "==> SEED_ONLY set; seeding synthetic demo data"
  python -m scripts.seed_demo
else
  echo "==> Ingesting live market data from yfinance"
  # Don't let a non-zero exit abort us — decide what's next from the row count.
  python -m backend.ingest || echo "    (ingest exited non-zero; will check row counts)"
  if [ "$(_quote_count)" -eq 0 ]; then
    echo "==> No quotes present after ingest; seeding synthetic demo data"
    python -m scripts.seed_demo
  fi
fi

count="$(_quote_count)"

echo
echo "==> Done. ${count} companies now have quotes in the target database."
if [ "$count" -eq 0 ]; then
  echo "    Something went wrong — no rows were written. Check the DATABASE_URL and errors above." >&2
  exit 1
fi
