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

## Notes & limitations

- **yfinance** is an unofficial Yahoo Finance scraper; it can rate-limit or briefly return empty data.
  Ingestion handles this per-ticker (skip + continue) and `INGEST_DELAY` paces requests. For production
  reliability you'd swap in an official feed (NSE/BSE bhavcopy, or a paid API) behind the same
  `ingest.py` interface — the rest of the stack is unchanged.
- Fundamentals like P/E and market cap reflect Yahoo's snapshot at ingest time.
- The synthetic seeder (`scripts/seed_demo.py`) is for demo/testing only; its numbers are plausible
  but **not real quotes**.
