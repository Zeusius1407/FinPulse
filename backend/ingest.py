"""Data ingestion — fetch from yfinance and write into the database.

Run a full refresh:
    python -m backend.ingest                 # 1 year of history (default)
    python -m backend.ingest --period 6mo    # less history = faster
    python -m backend.ingest --workers 12    # more parallelism for the quote calls

Speed strategy (the slow parts of ingestion are network + DB round-trips):
  1. All price history is pulled in ONE batched ``yf.download`` call (not 30
     separate ``.history`` requests).
  2. Per-company quotes/fundamentals (``.info``) are fetched concurrently with a
     thread pool.
  3. Price history is written with a per-ticker DELETE + a single bulk INSERT,
     instead of thousands of one-row-at-a-time upserts.

Quotes/companies still use ``session.merge`` (only ~30 rows, dialect-agnostic).
"""
from __future__ import annotations

import argparse
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pandas as pd
import yfinance as yf

from backend.config import COMPANIES, HISTORY_PERIOD, TICKERS
from backend.database import SessionLocal, init_db
from backend.models import Company, PriceHistory, Quote

DEFAULT_WORKERS = int(os.getenv("FINPULSE_WORKERS", "10"))


def _num(value) -> float | None:
    """Coerce a yfinance value to float, or None if missing/NaN."""
    try:
        if value is None:
            return None
        f = float(value)
        return None if f != f else f  # NaN check
    except (TypeError, ValueError):
        return None


def _int(value) -> int | None:
    f = _num(value)
    return int(f) if f is not None else None


def upsert_company(db, meta: dict, info: dict) -> None:
    db.merge(
        Company(
            ticker=meta["ticker"],
            name=meta["name"],
            sector=meta["sector"],
            industry=info.get("industry"),
            exchange="NSE",
            currency=info.get("currency", "INR"),
            updated_at=datetime.utcnow(),
        )
    )


def upsert_quote(db, ticker: str, info: dict) -> None:
    price = _num(info.get("currentPrice")) or _num(info.get("regularMarketPrice"))
    prev = _num(info.get("previousClose")) or _num(info.get("regularMarketPreviousClose"))
    change = round(price - prev, 2) if (price is not None and prev) else None
    change_pct = round((change / prev) * 100, 2) if (change is not None and prev) else None

    div_yield = _num(info.get("dividendYield"))
    # yfinance sometimes returns yield as a fraction, sometimes as a percent.
    if div_yield is not None and div_yield < 1:
        div_yield = round(div_yield * 100, 2)

    roe = _num(info.get("returnOnEquity"))
    if roe is not None:
        roe = round(roe * 100, 2)

    db.merge(
        Quote(
            ticker=ticker,
            price=price,
            previous_close=prev,
            change=change,
            change_pct=change_pct,
            day_high=_num(info.get("dayHigh")),
            day_low=_num(info.get("dayLow")),
            week52_high=_num(info.get("fiftyTwoWeekHigh")),
            week52_low=_num(info.get("fiftyTwoWeekLow")),
            volume=_int(info.get("volume")) or _int(info.get("regularMarketVolume")),
            market_cap=_int(info.get("marketCap")),
            pe_ratio=_num(info.get("trailingPE")),
            eps=_num(info.get("trailingEps")),
            pb_ratio=_num(info.get("priceToBook")),
            book_value=_num(info.get("bookValue")),
            dividend_yield=div_yield,
            beta=_num(info.get("beta")),
            roe=roe,
            updated_at=datetime.utcnow(),
        )
    )


def slice_history(batch: pd.DataFrame, ticker: str) -> pd.DataFrame | None:
    """Pull one ticker's OHLCV frame out of a batched ``yf.download`` result.

    ``yf.download(..., group_by="ticker")`` returns a column MultiIndex
    (ticker, field) for multiple tickers, or a flat frame for a single one.
    """
    if batch is None or batch.empty:
        return None
    try:
        if isinstance(batch.columns, pd.MultiIndex):
            if ticker not in batch.columns.get_level_values(0):
                return None
            df = batch[ticker]
        else:
            df = batch
    except (KeyError, TypeError):
        return None
    df = df.dropna(how="all")
    return df if not df.empty else None


def write_history(db, ticker: str, df: pd.DataFrame) -> int:
    """Replace a ticker's price history with one bulk insert.

    Because each run refetches the full period, deleting the ticker's rows and
    bulk-inserting is both correct and far faster than row-by-row upserts: it
    turns ~250 round-trips into one DELETE + one batched INSERT.
    """
    rows = []
    for idx, row in df.iterrows():
        close = _num(row.get("Close"))
        if close is None:
            continue  # skip holidays / non-trading rows
        rows.append(
            {
                "ticker": ticker,
                "date": idx.date(),
                "open": _num(row.get("Open")),
                "high": _num(row.get("High")),
                "low": _num(row.get("Low")),
                "close": close,
                "volume": _int(row.get("Volume")),
            }
        )
    if not rows:
        return 0
    # Flush any pending parent company/quote merges first. bulk_insert_mappings
    # issues the child INSERT immediately, and the session runs with
    # autoflush=False, so without this the price_history rows would reference a
    # companies row that hasn't been written yet — a FK violation on Postgres
    # (SQLite silently tolerated it because it doesn't enforce FKs by default).
    db.flush()
    db.query(PriceHistory).filter(PriceHistory.ticker == ticker).delete()
    db.bulk_insert_mappings(PriceHistory, rows)
    return len(rows)


def fetch_info(ticker: str) -> dict:
    """Fetch one ticker's quote/fundamentals. Returns {} on any failure."""
    try:
        return yf.Ticker(ticker).info or {}
    except Exception:  # noqa: BLE001
        return {}


def run(period: str = HISTORY_PERIOD, workers: int = DEFAULT_WORKERS) -> None:
    init_db()

    # 1) One batched request for ALL price history.
    print(f"Fetching {period} history for {len(TICKERS)} tickers in one batch...")
    batch = yf.download(
        TICKERS,
        period=period,
        group_by="ticker",
        auto_adjust=False,
        threads=True,
        progress=False,
    )

    # 2) Fetch quotes/fundamentals concurrently.
    print(f"Fetching quotes with {workers} parallel workers...")
    infos: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(fetch_info, t): t for t in TICKERS}
        for fut in as_completed(futures):
            infos[futures[fut]] = fut.result()

    # 3) Write everything. Quotes via merge (~30 rows); history via bulk insert.
    db = SessionLocal()
    ok, failed = 0, []
    try:
        for meta in COMPANIES:
            ticker = meta["ticker"]
            try:
                info = infos.get(ticker) or {}
                if not info.get("currentPrice") and not info.get("regularMarketPrice"):
                    raise ValueError("empty quote (possibly rate-limited)")

                df = slice_history(batch, ticker)
                if df is None:  # fall back to a single-ticker history call
                    df = yf.Ticker(ticker).history(period=period, auto_adjust=False)
                    df = df if df is not None and not df.empty else None

                upsert_company(db, meta, info)
                upsert_quote(db, ticker, info)
                bars = write_history(db, ticker, df) if df is not None else 0
                db.commit()
                ok += 1
                print(f"  ✓ {ticker:<14} price={info.get('currentPrice')!s:<10} bars={bars}")
            except Exception as exc:  # noqa: BLE001 — keep going on per-ticker errors
                db.rollback()
                failed.append((ticker, str(exc)))
                print(f"  ✗ {ticker:<14} {exc}")
    finally:
        db.close()

    print(f"\nDone. {ok} succeeded, {len(failed)} failed.")
    for t, e in failed:
        print(f"   failed: {t} -> {e}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="FinPulse data ingestion")
    ap.add_argument("--period", default=HISTORY_PERIOD, help="history period (e.g. 1y, 6mo)")
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                    help="parallel workers for quote fetches")
    args = ap.parse_args()
    print("Ingesting market data from yfinance...")
    run(period=args.period, workers=args.workers)