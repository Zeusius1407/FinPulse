"""Data ingestion — fetch from yfinance and upsert into the database.

Run a full refresh:
    python -m backend.ingest

This is the script you run on a machine/host *with internet access* (locally,
or as a scheduled job on the deploy target). It:
  1. ensures the company rows exist,
  2. pulls the latest quote + fundamentals for each ticker,
  3. pulls daily OHLCV history,
and upserts everything so repeated runs update rows in place rather than
duplicating them.

`session.merge()` is used for upserts because it is dialect-agnostic (works on
both SQLite locally and Postgres in production).
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime

import yfinance as yf

from backend.config import COMPANIES, HISTORY_PERIOD, INGEST_DELAY, SECTOR_BY_TICKER
from backend.database import SessionLocal, init_db
from backend.models import Company, PriceHistory, Quote


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


def upsert_history(db, ticker: str, tk: yf.Ticker, period: str) -> int:
    hist = tk.history(period=period, auto_adjust=False)
    if hist is None or hist.empty:
        return 0
    n = 0
    for idx, row in hist.iterrows():
        db.merge(
            PriceHistory(
                ticker=ticker,
                date=idx.date(),
                open=_num(row.get("Open")),
                high=_num(row.get("High")),
                low=_num(row.get("Low")),
                close=_num(row.get("Close")),
                volume=_int(row.get("Volume")),
            )
        )
        n += 1
    return n


def run(period: str = HISTORY_PERIOD) -> None:
    init_db()
    db = SessionLocal()
    ok, failed = 0, []
    try:
        for meta in COMPANIES:
            ticker = meta["ticker"]
            try:
                tk = yf.Ticker(ticker)
                info = tk.info or {}
                # yfinance occasionally returns an empty info dict on throttling.
                if not info.get("currentPrice") and not info.get("regularMarketPrice"):
                    raise ValueError("empty quote (possibly rate-limited)")

                upsert_company(db, meta, info)
                upsert_quote(db, ticker, info)
                bars = upsert_history(db, ticker, tk, period)
                db.commit()
                ok += 1
                print(f"  ✓ {ticker:<14} price={info.get('currentPrice')!s:<10} bars={bars}")
            except Exception as exc:  # noqa: BLE001 — keep going on per-ticker errors
                db.rollback()
                failed.append((ticker, str(exc)))
                print(f"  ✗ {ticker:<14} {exc}")
            time.sleep(INGEST_DELAY)
    finally:
        db.close()

    print(f"\nDone. {ok} succeeded, {len(failed)} failed.")
    for t, e in failed:
        print(f"   failed: {t} -> {e}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="FinPulse data ingestion")
    ap.add_argument("--period", default=HISTORY_PERIOD, help="history period (e.g. 1y)")
    args = ap.parse_args()
    print("Ingesting market data from yfinance...")
    run(period=args.period)
