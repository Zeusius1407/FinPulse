# FinPulse 📈

A stock-market monitoring platform that aggregates **live and historical market data** plus
**fundamental metrics** for **30 NSE-listed Indian companies** into a single, interactive dashboard.

Built as: **yfinance → SQLAlchemy/DB → FastAPI REST API → Streamlit dashboard.**

```
┌────────────┐   ingest    ┌──────────────┐   SQLAlchemy   ┌─────────────┐   HTTP/JSON   ┌──────────────┐
│  yfinance  │ ──────────▶ │   Database   │ ◀────────────▶ │  FastAPI    │ ◀───────────▶ │  Streamlit   │
│ (NSE data) │  upsert     │ SQLite / PG  │   ORM models   │  REST API   │   requests    │  Dashboard   │
└────────────┘             └──────────────┘                └─────────────┘               └──────────────┘
   backend/ingest.py        backend/models.py               backend/main.py               dashboard/app.py
```

The dashboard deliberately talks to the **REST API** (not the DB directly), so the project
demonstrates the full request flow end-to-end.

---

## What it does (MVP coverage)

| Requirement | Where |
|---|---|
| Track ≥ 20 listed companies | **30** NSE large caps — `backend/config.py` |
| Live + historical market data | `backend/ingest.py` (yfinance) |
| Stock price, market cap, P/E, EPS (+ extras) | `quotes` table — also 52W range, P/B, book value, dividend yield, beta, ROE, volume |
| Store in a database, updatable efficiently | SQLAlchemy ORM, upsert-in-place — `backend/models.py` |
| ≥ 3 REST endpoints | **7 endpoints** — `backend/main.py` |
| Dashboard: history charts, fundamentals, comparison | `dashboard/app.py` (3 tabs) |
| Deploy online | Render (API) + Streamlit Cloud (dashboard) — see below |

**Beyond the MVP:** sector aggregation, market-breadth summary (advancers/decliners, top movers),
candlestick + 20-day MA + volume charts, normalised multi-stock price comparison, an optional
background scheduler that auto-refreshes data, Swagger/ReDoc auto-docs, and a synthetic-data seeder
so the app runs even with no internet.

---

## Project structure

```
finpulse/
├── backend/
│   ├── config.py      # settings + the 30-company universe
│   ├── database.py    # SQLAlchemy engine / session / Base
│   ├── models.py      # ORM: Company, Quote, PriceHistory
│   ├── schemas.py     # Pydantic response models
│   ├── crud.py        # query layer (kept out of the endpoints)
│   ├── main.py        # FastAPI app — 7 REST endpoints
│   ├── ingest.py      # fetch from yfinance + upsert
│   └── scheduler.py   # optional periodic auto-refresh
├── dashboard/
│   ├── app.py         # Streamlit dashboard (3 tabs)
│   └── api_client.py  # thin client for the REST API
├── scripts/
│   └── seed_demo.py   # synthetic data for offline demo / testing
├── data/              # SQLite DB lives here (gitignored)
├── requirements.txt
├── render.yaml        # one-click Render blueprint (API + Postgres)
├── Procfile
├── run_local.sh       # seed + API + dashboard in one command
└── README.md
```

---

## Quick start (local)

Requires Python 3.10+.

```bash
git clone <your-repo-url> finpulse && cd finpulse
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**Option A — one command (synthetic demo data, no internet needed):**

```bash
bash run_local.sh
```

**Option B — live data, run each piece yourself:**

```bash
# 1) create tables + pull real data from yfinance (needs internet)
python -m backend.ingest

# 2) start the API           -> http://127.0.0.1:8000  (docs at /docs)
uvicorn backend.main:app --reload

# 3) in a second terminal, start the dashboard -> http://localhost:8501
export FINPULSE_API_URL="http://127.0.0.1:8000"   # Windows: set FINPULSE_API_URL=...
streamlit run dashboard/app.py
```

> Tip: `python -m scripts.seed_demo` populates believable **synthetic** data instantly —
> handy when yfinance is rate-limiting or you're offline.

---

## REST API

Base URL (local): `http://127.0.0.1:8000` · interactive docs at `/docs` (Swagger) and `/redoc`.

| Method | Endpoint | Description |
|---|---|---|
| GET | `/stocks` | All companies + latest quote. Query: `sector`, `sort_by`, `order`, `limit`. |
| GET | `/stocks/{ticker}` | Full detail (metadata + quote) for one company. |
| GET | `/stocks/{ticker}/history` | Daily OHLCV. Query: `period` = `5d,1mo,3mo,6mo,1y,max`. |
| GET | `/market-summary` | Breadth, total market cap, avg P/E, top gainers/losers, sectors. |
| GET | `/compare?tickers=A,B,C` | Side-by-side detail for several companies. |
| GET | `/sectors` | Sector-level aggregates (market cap, avg P/E, avg move). |
| GET | `/` | Service info / health check. |

Examples:

```bash
curl "http://127.0.0.1:8000/stocks?sector=IT&sort_by=market_cap&limit=5"
curl "http://127.0.0.1:8000/stocks/RELIANCE.NS"
curl "http://127.0.0.1:8000/stocks/TCS.NS/history?period=6mo"
curl "http://127.0.0.1:8000/compare?tickers=RELIANCE.NS,TCS.NS,INFY.NS"
curl "http://127.0.0.1:8000/market-summary"
```

---

## Database schema

Three normalised tables keep fast-changing data separate from the append-only time series, so a
live refresh touches **one row per company** and charts read a compact indexed range.

- **`companies`** — static-ish metadata: `ticker` (PK), `name`, `sector`, `industry`, `exchange`, `currency`.
- **`quotes`** — latest snapshot, **one row per ticker, upserted in place**: `price`, `previous_close`,
  `change`, `change_pct`, day/52-week highs & lows, `volume`, `market_cap`, `pe_ratio`, `eps`,
  `pb_ratio`, `book_value`, `dividend_yield`, `beta`, `roe`, `updated_at`.
- **`price_history`** — daily OHLCV, **unique on `(ticker, date)`**, indexed for range queries.

Upserts use `session.merge()`, which is dialect-agnostic, so the exact same code runs on **SQLite**
locally and **Postgres/Supabase** in production — only `DATABASE_URL` changes.

---

## Configuration (env vars)

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | local SQLite file | Set to a Postgres/Supabase URL in production. |
| `FINPULSE_API_URL` | `http://127.0.0.1:8000` | URL the dashboard calls. |
| `FINPULSE_HISTORY_PERIOD` | `1y` | History pulled per ingest. |
| `FINPULSE_INGEST_DELAY` | `0.4` | Seconds between yfinance calls (avoid throttling). |
| `FINPULSE_ENABLE_SCHEDULER` | `0` | `1` enables in-process auto-refresh. |
| `FINPULSE_REFRESH_HOURS` | `6` | Refresh interval when scheduler is on. |

A `postgres://` URL (as Render/Heroku hand out) is auto-normalised to the SQLAlchemy form.

---

## Deploy online

**Recommended free split:** API + Postgres on **Render**, dashboard on **Streamlit Community Cloud**.

**1. API + database on Render**
- Push this repo to GitHub.
- Render → **New → Blueprint** → select the repo. `render.yaml` provisions a free Postgres DB and the
  API web service, wiring `DATABASE_URL` automatically.
- Once live, open the service **Shell** and populate data once: `python -m backend.ingest`
  (or leave the scheduler enabled — it refreshes every 12h and seeds on boot).
- Note the API URL, e.g. `https://finpulse-api.onrender.com`.

**2. Dashboard on Streamlit Community Cloud**
- streamlit.io/cloud → **New app** → this repo → main file `dashboard/app.py`.
- In the app's **Secrets/Variables**, set `FINPULSE_API_URL` to your Render API URL.
- Deploy. The dashboard is now public and reads from your deployed API.

**Persistent free DB alternative:** create a project on **Supabase**, copy its Postgres connection
string into `DATABASE_URL` on Render (Render's own free Postgres is wiped after 30 days).

Everything also runs together on a single host (Railway, a VPS, Hugging Face Spaces): run
`uvicorn backend.main:app` and `streamlit run dashboard/app.py`, pointing `FINPULSE_API_URL` at the API.

---

## Notes & limitations

- **yfinance** is an unofficial Yahoo Finance scraper; it can rate-limit or briefly return empty data.
  Ingestion handles this per-ticker (skip + continue) and `INGEST_DELAY` paces requests. For production
  reliability you'd swap in an official feed (NSE/BSE bhavcopy, or a paid API) behind the same
  `ingest.py` interface — the rest of the stack is unchanged.
- Fundamentals like P/E and market cap reflect Yahoo's snapshot at ingest time.
- The synthetic seeder (`scripts/seed_demo.py`) is for demo/testing only; its numbers are plausible
  but **not real quotes**.
