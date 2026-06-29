"""ORM models.

Schema design (3 tables, normalised for efficient updates + retrieval):

  companies      -- relatively static metadata (one row per ticker)
  quotes         -- latest live snapshot (one row per ticker, upserted in place)
  price_history  -- daily OHLCV time series (one row per ticker+date)

Keeping the fast-changing snapshot (`quotes`) separate from the append-only
time series (`price_history`) means a live refresh touches exactly one row per
company, while charts read a compact indexed range from `price_history`.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Float,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class Company(Base):
    __tablename__ = "companies"

    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(60))
    industry: Mapped[str | None] = mapped_column(String(120))
    exchange: Mapped[str | None] = mapped_column(String(20), default="NSE")
    currency: Mapped[str | None] = mapped_column(String(8), default="INR")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now()
    )

    quote: Mapped["Quote"] = relationship(
        back_populates="company", uselist=False, cascade="all, delete-orphan"
    )
    prices: Mapped[list["PriceHistory"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )


class Quote(Base):
    """Latest snapshot of price + fundamentals. One row per ticker (upserted)."""

    __tablename__ = "quotes"

    ticker: Mapped[str] = mapped_column(
        String(20), ForeignKey("companies.ticker", ondelete="CASCADE"), primary_key=True
    )

    # Price block
    price: Mapped[float | None] = mapped_column(Float)
    previous_close: Mapped[float | None] = mapped_column(Float)
    change: Mapped[float | None] = mapped_column(Float)
    change_pct: Mapped[float | None] = mapped_column(Float)
    day_high: Mapped[float | None] = mapped_column(Float)
    day_low: Mapped[float | None] = mapped_column(Float)
    week52_high: Mapped[float | None] = mapped_column(Float)
    week52_low: Mapped[float | None] = mapped_column(Float)
    volume: Mapped[int | None] = mapped_column(BigInteger)

    # Fundamentals block (MVP requires market cap, P/E, EPS)
    market_cap: Mapped[int | None] = mapped_column(BigInteger)
    pe_ratio: Mapped[float | None] = mapped_column(Float)
    eps: Mapped[float | None] = mapped_column(Float)
    pb_ratio: Mapped[float | None] = mapped_column(Float)
    book_value: Mapped[float | None] = mapped_column(Float)
    dividend_yield: Mapped[float | None] = mapped_column(Float)
    beta: Mapped[float | None] = mapped_column(Float)
    roe: Mapped[float | None] = mapped_column(Float)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now()
    )

    company: Mapped["Company"] = relationship(back_populates="quote")


class PriceHistory(Base):
    """Daily OHLCV bars. Unique per (ticker, date)."""

    __tablename__ = "price_history"

    # Composite natural primary key (ticker, date). This is what makes
    # ``session.merge()`` upsert correctly: merge matches existing rows by
    # primary key, so a re-ingest of the same trading day UPDATES the row
    # instead of blindly INSERTing and tripping a uniqueness violation.
    ticker: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("companies.ticker", ondelete="CASCADE"),
        primary_key=True,
    )
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[float | None] = mapped_column(Float)
    high: Mapped[float | None] = mapped_column(Float)
    low: Mapped[float | None] = mapped_column(Float)
    close: Mapped[float | None] = mapped_column(Float)
    volume: Mapped[int | None] = mapped_column(BigInteger)

    company: Mapped["Company"] = relationship(back_populates="prices")
