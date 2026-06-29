"""FastAPI application — the REST layer of FinPulse.

Endpoints (all read-only GET; the MVP needs >= 3, this exposes 7):

  GET /                       service info / health
  GET /stocks                 list tracked companies + latest quote (filter/sort)
  GET /stocks/{ticker}        full detail for one company
  GET /stocks/{ticker}/history historical OHLCV for charting
  GET /market-summary         aggregate view (breadth, top movers, sectors)
  GET /compare                side-by-side fundamentals for several tickers
  GET /sectors                sector-level aggregates

Run locally:
  uvicorn backend.main:app --reload
Interactive docs at /docs (Swagger) and /redoc.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from backend import crud, scheduler, schemas
from backend.config import API_TITLE, API_VERSION
from backend.crud import PERIOD_DAYS
from backend.database import get_db, init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Ensure tables exist; ingestion populates the data.
    init_db()
    scheduler.maybe_start()  # no-op unless FINPULSE_ENABLE_SCHEDULER=1
    yield
    scheduler.shutdown()


app = FastAPI(
    title=API_TITLE,
    version=API_VERSION,
    description="Aggregated market data and fundamentals for 30 NSE large caps.",
    lifespan=lifespan,
)

# Allow the Streamlit dashboard (a different origin) to call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "service": API_TITLE,
        "version": API_VERSION,
        "docs": "/docs",
        "endpoints": [
            "/stocks",
            "/stocks/{ticker}",
            "/stocks/{ticker}/history",
            "/market-summary",
            "/compare",
            "/sectors",
        ],
    }


@app.get("/stocks", response_model=list[schemas.StockSummary], tags=["stocks"])
def get_stocks(
    db: Session = Depends(get_db),
    sector: str | None = Query(None, description="Filter by sector, e.g. 'IT'"),
    sort_by: str = Query(
        "market_cap",
        description="market_cap | change_pct | pe_ratio | price | ticker",
    ),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(100, ge=1, le=100),
):
    """List all tracked companies with their latest quote."""
    companies = crud.list_companies(db)
    rows = [crud.to_summary(c) for c in companies]

    if sector:
        rows = [r for r in rows if (r.sector or "").lower() == sector.lower()]

    key_funcs = {
        "market_cap": lambda r: r.market_cap or 0,
        "change_pct": lambda r: r.change_pct or 0,
        "pe_ratio": lambda r: r.pe_ratio or 0,
        "price": lambda r: r.price or 0,
        "ticker": lambda r: r.ticker,
    }
    key = key_funcs.get(sort_by, key_funcs["market_cap"])
    rows.sort(key=key, reverse=(order == "desc"))
    return rows[:limit]


@app.get("/market-summary", response_model=schemas.MarketSummary, tags=["market"])
def get_market_summary(db: Session = Depends(get_db)):
    """Whole-market breadth, top movers and sector breakdown."""
    return crud.market_summary(db)


@app.get("/sectors", response_model=list[schemas.SectorAgg], tags=["market"])
def get_sectors(db: Session = Depends(get_db)):
    """Sector-level aggregates (market cap, average P/E, average move)."""
    return crud.market_summary(db).sectors


@app.get("/compare", response_model=list[schemas.StockDetail], tags=["stocks"])
def compare(
    tickers: str = Query(..., description="Comma-separated, e.g. RELIANCE.NS,TCS.NS"),
    db: Session = Depends(get_db),
):
    """Return full detail for several companies for side-by-side comparison."""
    wanted = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not wanted:
        raise HTTPException(400, "Provide at least one ticker.")
    out: list = []
    for t in wanted:
        c = crud.get_company(db, t)
        if c is not None:
            out.append(c)
    if not out:
        raise HTTPException(404, "None of the requested tickers were found.")
    return out


@app.get("/stocks/{ticker}", response_model=schemas.StockDetail, tags=["stocks"])
def get_stock(ticker: str, db: Session = Depends(get_db)):
    """Full detail (metadata + latest quote) for one company."""
    c = crud.get_company(db, ticker)
    if c is None:
        raise HTTPException(404, f"Ticker '{ticker}' not tracked.")
    return c


@app.get(
    "/stocks/{ticker}/history",
    response_model=schemas.PriceHistoryOut,
    tags=["stocks"],
)
def get_stock_history(
    ticker: str,
    period: str = Query("1y", description=f"One of: {', '.join(PERIOD_DAYS)}"),
    db: Session = Depends(get_db),
):
    """Daily OHLCV history for a company, used to draw price charts."""
    if period not in PERIOD_DAYS:
        raise HTTPException(400, f"period must be one of {list(PERIOD_DAYS)}")
    if crud.get_company(db, ticker) is None:
        raise HTTPException(404, f"Ticker '{ticker}' not tracked.")
    points = crud.get_history(db, ticker, period)
    return schemas.PriceHistoryOut(
        ticker=ticker.upper(),
        period=period,
        points=[schemas.PricePoint.model_validate(p) for p in points],
    )
