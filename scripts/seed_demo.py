"""Seed the database with realistic *synthetic* data.

Use this when you want to run/demo FinPulse without internet access (yfinance
unreachable) or to quickly populate a fresh DB for development. Prices and
fundamentals are anchored to roughly plausible values for each company, and a
~1 year daily history is generated with a reproducible random walk.

    python -m scripts.seed_demo

For real market data instead, run:  python -m backend.ingest
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta

from backend.config import COMPANIES
from backend.database import SessionLocal, init_db
from backend.models import Company, PriceHistory, Quote

# Anchor values: (approx price INR, approx market cap INR, P/E, sector beta-ish vol)
# These are ballpark figures for a believable demo, not live quotes.
ANCHORS: dict[str, tuple[float, int, float, float]] = {
    "RELIANCE.NS":   (2950,  19_950_000_000_000, 28.5, 0.018),
    "TCS.NS":        (4100,  14_800_000_000_000, 31.0, 0.015),
    "HDFCBANK.NS":   (1680,  12_700_000_000_000, 19.8, 0.016),
    "INFY.NS":       (1850,   7_650_000_000_000, 27.4, 0.017),
    "ICICIBANK.NS":  (1180,   8_300_000_000_000, 18.2, 0.017),
    "HINDUNILVR.NS": (2450,   5_750_000_000_000, 55.0, 0.013),
    "SBIN.NS":       (820,    7_320_000_000_000,  9.6, 0.020),
    "BHARTIARTL.NS": (1530,   9_100_000_000_000, 62.0, 0.016),
    "ITC.NS":        (470,    5_880_000_000_000, 27.0, 0.013),
    "KOTAKBANK.NS":  (1790,   3_560_000_000_000, 18.9, 0.017),
    "LT.NS":         (3650,   5_020_000_000_000, 36.0, 0.018),
    "BAJFINANCE.NS": (7200,   4_460_000_000_000, 30.5, 0.022),
    "AXISBANK.NS":   (1130,   3_490_000_000_000, 13.4, 0.019),
    "ASIANPAINT.NS": (2880,   2_760_000_000_000, 52.0, 0.016),
    "MARUTI.NS":     (12600,  3_960_000_000_000, 28.0, 0.018),
    "SUNPHARMA.NS":  (1720,   4_130_000_000_000, 38.0, 0.015),
    "TITAN.NS":      (3380,   3_000_000_000_000, 88.0, 0.019),
    "ULTRACEMCO.NS": (11200,  3_230_000_000_000, 47.0, 0.017),
    "WIPRO.NS":      (540,    2_820_000_000_000, 24.0, 0.018),
    "NESTLEIND.NS":  (2480,   2_390_000_000_000, 75.0, 0.012),
    "HCLTECH.NS":    (1760,   4_780_000_000_000, 27.5, 0.016),
    "NTPC.NS":       (360,    3_490_000_000_000, 16.5, 0.018),
    "POWERGRID.NS":  (320,    2_980_000_000_000, 18.0, 0.016),
    "TATAMOTORS.NS": (980,    3_600_000_000_000, 11.2, 0.024),
    "TATASTEEL.NS":  (148,    1_850_000_000_000, 24.0, 0.022),
    "ADANIENT.NS":   (2380,   2_750_000_000_000, 65.0, 0.030),
    "ONGC.NS":       (245,    3_080_000_000_000,  7.4, 0.020),
    "COALINDIA.NS":  (410,    2_530_000_000_000,  8.1, 0.019),
    "JSWSTEEL.NS":   (920,    2_250_000_000_000, 60.0, 0.021),
    "GRASIM.NS":     (2560,   1_730_000_000_000, 30.0, 0.018),
}

TRADING_DAYS = 252  # ~1 year of trading sessions


def _gen_history(end_price: float, vol: float, rng: random.Random):
    """Generate ~1y of daily OHLCV ending near `end_price` via a random walk.

    We walk backwards from today so the latest close matches the live quote.
    """
    bars: list[dict] = []
    price = end_price
    day = date.today()
    produced = 0
    while produced < TRADING_DAYS:
        if day.weekday() < 5:  # Mon-Fri only
            drift = rng.gauss(0, vol)
            prev = price / (1 + drift) if (1 + drift) != 0 else price
            high = max(price, prev) * (1 + abs(rng.gauss(0, vol / 2)))
            low = min(price, prev) * (1 - abs(rng.gauss(0, vol / 2)))
            volume = int(abs(rng.gauss(1, 0.4)) * 4_000_000)
            bars.append(
                {
                    "date": day,
                    "open": round(prev, 2),
                    "high": round(high, 2),
                    "low": round(low, 2),
                    "close": round(price, 2),
                    "volume": volume,
                }
            )
            price = prev
            produced += 1
        day -= timedelta(days=1)
    bars.reverse()
    return bars


def run(seed: int = 42) -> None:
    init_db()
    db = SessionLocal()
    try:
        # Clean slate so re-seeding is idempotent.
        db.query(PriceHistory).delete()
        db.query(Quote).delete()
        db.query(Company).delete()
        db.commit()

        for i, meta in enumerate(COMPANIES):
            ticker = meta["ticker"]
            rng = random.Random(seed + i)
            anchor = ANCHORS.get(ticker, (1000, 1_000_000_000_000, 25.0, 0.018))
            price, mcap, pe, vol = anchor

            bars = _gen_history(price, vol, rng)
            last, prev = bars[-1], bars[-2]
            close = last["close"]
            prev_close = prev["close"]
            change = round(close - prev_close, 2)
            change_pct = round(change / prev_close * 100, 2)
            eps = round(close / pe, 2)
            book_value = round(close / rng.uniform(2.0, 6.0), 2)

            db.add(
                Company(
                    ticker=ticker,
                    name=meta["name"],
                    sector=meta["sector"],
                    industry=meta["sector"],
                    exchange="NSE",
                    currency="INR",
                    updated_at=datetime.utcnow(),
                )
            )
            db.add(
                Quote(
                    ticker=ticker,
                    price=close,
                    previous_close=prev_close,
                    change=change,
                    change_pct=change_pct,
                    day_high=last["high"],
                    day_low=last["low"],
                    week52_high=round(max(b["high"] for b in bars), 2),
                    week52_low=round(min(b["low"] for b in bars), 2),
                    volume=last["volume"],
                    market_cap=mcap,
                    pe_ratio=pe,
                    eps=eps,
                    pb_ratio=round(close / book_value, 2),
                    book_value=book_value,
                    dividend_yield=round(rng.uniform(0.3, 3.5), 2),
                    beta=round(rng.uniform(0.6, 1.6), 2),
                    roe=round(rng.uniform(8, 28), 2),
                    updated_at=datetime.utcnow(),
                )
            )
            db.bulk_save_objects(
                [PriceHistory(ticker=ticker, **b) for b in bars]
            )
            db.commit()
            print(f"  seeded {ticker:<14} close={close} bars={len(bars)}")
    finally:
        db.close()
    print(f"\nSeeded {len(COMPANIES)} companies with synthetic data.")


if __name__ == "__main__":
    print("Seeding FinPulse with synthetic demo data...")
    run()
