"""Pydantic schemas for API responses."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class QuoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    price: float | None = None
    previous_close: float | None = None
    change: float | None = None
    change_pct: float | None = None
    day_high: float | None = None
    day_low: float | None = None
    week52_high: float | None = None
    week52_low: float | None = None
    volume: int | None = None
    market_cap: int | None = None
    pe_ratio: float | None = None
    eps: float | None = None
    pb_ratio: float | None = None
    book_value: float | None = None
    dividend_yield: float | None = None
    beta: float | None = None
    roe: float | None = None
    updated_at: datetime | None = None


class StockSummary(BaseModel):
    """Flattened company + key quote fields, used in list endpoints."""

    ticker: str
    name: str
    sector: str | None = None
    price: float | None = None
    change: float | None = None
    change_pct: float | None = None
    market_cap: int | None = None
    pe_ratio: float | None = None
    eps: float | None = None
    updated_at: datetime | None = None


class StockDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ticker: str
    name: str
    sector: str | None = None
    industry: str | None = None
    exchange: str | None = None
    currency: str | None = None
    quote: QuoteOut | None = None


class PricePoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: int | None = None


class PriceHistoryOut(BaseModel):
    ticker: str
    period: str
    points: list[PricePoint]


class SectorAgg(BaseModel):
    sector: str
    count: int
    total_market_cap: int
    avg_pe: float | None = None
    avg_change_pct: float | None = None


class MarketSummary(BaseModel):
    companies_tracked: int
    total_market_cap: int
    advancers: int
    decliners: int
    unchanged: int
    avg_pe: float | None = None
    top_gainers: list[StockSummary]
    top_losers: list[StockSummary]
    sectors: list[SectorAgg]
    last_updated: datetime | None = None
