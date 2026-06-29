"""Database read helpers used by the API layer.

Keeping queries here (rather than inline in endpoints) keeps the FastAPI
handlers thin and makes the data access testable in isolation.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from backend import models, schemas

# Map a human period string to a rough number of calendar days.
PERIOD_DAYS = {
    "5d": 5,
    "1mo": 31,
    "3mo": 93,
    "6mo": 186,
    "1y": 366,
    "max": 100_000,
}


def list_companies(db: Session) -> list[models.Company]:
    stmt = select(models.Company).options(joinedload(models.Company.quote)).order_by(
        models.Company.ticker
    )
    return list(db.scalars(stmt).unique())


def get_company(db: Session, ticker: str) -> models.Company | None:
    stmt = (
        select(models.Company)
        .options(joinedload(models.Company.quote))
        .where(models.Company.ticker == ticker.upper())
    )
    return db.scalars(stmt).unique().one_or_none()


def to_summary(c: models.Company) -> schemas.StockSummary:
    q = c.quote
    return schemas.StockSummary(
        ticker=c.ticker,
        name=c.name,
        sector=c.sector,
        price=q.price if q else None,
        change=q.change if q else None,
        change_pct=q.change_pct if q else None,
        market_cap=q.market_cap if q else None,
        pe_ratio=q.pe_ratio if q else None,
        eps=q.eps if q else None,
        updated_at=q.updated_at if q else None,
    )


def get_history(
    db: Session, ticker: str, period: str = "1y"
) -> list[models.PriceHistory]:
    days = PERIOD_DAYS.get(period, 366)
    cutoff = date.today() - timedelta(days=days)
    stmt = (
        select(models.PriceHistory)
        .where(
            models.PriceHistory.ticker == ticker.upper(),
            models.PriceHistory.date >= cutoff,
        )
        .order_by(models.PriceHistory.date)
    )
    return list(db.scalars(stmt))


def market_summary(db: Session, top_n: int = 5) -> schemas.MarketSummary:
    companies = list_companies(db)
    summaries = [to_summary(c) for c in companies if c.quote is not None]

    total_mcap = sum(s.market_cap or 0 for s in summaries)
    advancers = sum(1 for s in summaries if (s.change_pct or 0) > 0)
    decliners = sum(1 for s in summaries if (s.change_pct or 0) < 0)
    unchanged = sum(1 for s in summaries if (s.change_pct or 0) == 0)

    pes = [s.pe_ratio for s in summaries if s.pe_ratio and s.pe_ratio > 0]
    avg_pe = round(sum(pes) / len(pes), 2) if pes else None

    ranked = sorted(summaries, key=lambda s: (s.change_pct or 0), reverse=True)
    top_gainers = ranked[:top_n]
    top_losers = list(reversed(ranked[-top_n:]))

    # Sector aggregation
    sector_map: dict[str, list[schemas.StockSummary]] = {}
    for s in summaries:
        sector_map.setdefault(s.sector or "Other", []).append(s)

    sectors: list[schemas.SectorAgg] = []
    for name, items in sorted(sector_map.items()):
        s_pes = [i.pe_ratio for i in items if i.pe_ratio and i.pe_ratio > 0]
        s_chg = [i.change_pct for i in items if i.change_pct is not None]
        sectors.append(
            schemas.SectorAgg(
                sector=name,
                count=len(items),
                total_market_cap=sum(i.market_cap or 0 for i in items),
                avg_pe=round(sum(s_pes) / len(s_pes), 2) if s_pes else None,
                avg_change_pct=round(sum(s_chg) / len(s_chg), 2) if s_chg else None,
            )
        )
    sectors.sort(key=lambda x: x.total_market_cap, reverse=True)

    last_updated = max(
        (c.quote.updated_at for c in companies if c.quote and c.quote.updated_at),
        default=None,
    )

    return schemas.MarketSummary(
        companies_tracked=len(summaries),
        total_market_cap=total_mcap,
        advancers=advancers,
        decliners=decliners,
        unchanged=unchanged,
        avg_pe=avg_pe,
        top_gainers=top_gainers,
        top_losers=top_losers,
        sectors=sectors,
        last_updated=last_updated,
    )
