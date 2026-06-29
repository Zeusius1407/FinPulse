"""Central configuration for FinPulse.

Reads settings from environment variables (with sane local defaults) and
defines the universe of companies the platform tracks.
"""
from __future__ import annotations

import os

# --------------------------------------------------------------------------- #
# Database
# --------------------------------------------------------------------------- #
# Local default is a SQLite file. In production, set DATABASE_URL to a Postgres
# / Supabase connection string, e.g.
#   postgresql+psycopg2://user:pass@host:5432/dbname
# The rest of the app is DB-agnostic because it goes through SQLAlchemy.
_DEFAULT_SQLITE = "sqlite:///" + os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "finpulse.db"
)
DATABASE_URL: str = os.getenv("DATABASE_URL", _DEFAULT_SQLITE)

# Render/Heroku hand out a legacy "postgres://" scheme that SQLAlchemy 2.x
# rejects. Normalise it to the driver-qualified form.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)

# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
API_TITLE = "FinPulse API"
API_VERSION = "1.0.0"

# How many days of price history to pull on ingest.
HISTORY_PERIOD = os.getenv("FINPULSE_HISTORY_PERIOD", "1y")

# Politeness delay (seconds) between yfinance calls to avoid rate limiting.
INGEST_DELAY = float(os.getenv("FINPULSE_INGEST_DELAY", "0.4"))

# --------------------------------------------------------------------------- #
# Company universe — 30 liquid NSE large caps (the MVP needs >= 20).
# yfinance uses the ".NS" suffix for NSE-listed equities.
# Sector tags are kept locally so the dashboard works even if a provider omits
# them, and so sector aggregation is consistent.
# --------------------------------------------------------------------------- #
COMPANIES: list[dict[str, str]] = [
    {"ticker": "RELIANCE.NS",   "name": "Reliance Industries",        "sector": "Energy"},
    {"ticker": "TCS.NS",        "name": "Tata Consultancy Services",  "sector": "IT"},
    {"ticker": "HDFCBANK.NS",   "name": "HDFC Bank",                  "sector": "Financials"},
    {"ticker": "INFY.NS",       "name": "Infosys",                    "sector": "IT"},
    {"ticker": "ICICIBANK.NS",  "name": "ICICI Bank",                 "sector": "Financials"},
    {"ticker": "HINDUNILVR.NS", "name": "Hindustan Unilever",         "sector": "FMCG"},
    {"ticker": "SBIN.NS",       "name": "State Bank of India",        "sector": "Financials"},
    {"ticker": "BHARTIARTL.NS", "name": "Bharti Airtel",              "sector": "Telecom"},
    {"ticker": "ITC.NS",        "name": "ITC",                        "sector": "FMCG"},
    {"ticker": "KOTAKBANK.NS",  "name": "Kotak Mahindra Bank",        "sector": "Financials"},
    {"ticker": "LT.NS",         "name": "Larsen & Toubro",            "sector": "Industrials"},
    {"ticker": "BAJFINANCE.NS", "name": "Bajaj Finance",              "sector": "Financials"},
    {"ticker": "AXISBANK.NS",   "name": "Axis Bank",                  "sector": "Financials"},
    {"ticker": "ASIANPAINT.NS", "name": "Asian Paints",               "sector": "Materials"},
    {"ticker": "MARUTI.NS",     "name": "Maruti Suzuki",              "sector": "Auto"},
    {"ticker": "SUNPHARMA.NS",  "name": "Sun Pharmaceutical",         "sector": "Pharma"},
    {"ticker": "TITAN.NS",      "name": "Titan Company",              "sector": "Consumer"},
    {"ticker": "ULTRACEMCO.NS", "name": "UltraTech Cement",           "sector": "Materials"},
    {"ticker": "WIPRO.NS",      "name": "Wipro",                      "sector": "IT"},
    {"ticker": "NESTLEIND.NS",  "name": "Nestle India",               "sector": "FMCG"},
    {"ticker": "HCLTECH.NS",    "name": "HCL Technologies",           "sector": "IT"},
    {"ticker": "NTPC.NS",       "name": "NTPC",                       "sector": "Energy"},
    {"ticker": "POWERGRID.NS",  "name": "Power Grid Corporation",     "sector": "Energy"},
    {"ticker": "TATAMOTORS.NS", "name": "Tata Motors",                "sector": "Auto"},
    {"ticker": "TATASTEEL.NS",  "name": "Tata Steel",                 "sector": "Materials"},
    {"ticker": "ADANIENT.NS",   "name": "Adani Enterprises",          "sector": "Industrials"},
    {"ticker": "ONGC.NS",       "name": "Oil & Natural Gas Corp",     "sector": "Energy"},
    {"ticker": "COALINDIA.NS",  "name": "Coal India",                 "sector": "Energy"},
    {"ticker": "JSWSTEEL.NS",   "name": "JSW Steel",                  "sector": "Materials"},
    {"ticker": "GRASIM.NS",     "name": "Grasim Industries",          "sector": "Materials"},
]

TICKERS: list[str] = [c["ticker"] for c in COMPANIES]
SECTOR_BY_TICKER: dict[str, str] = {c["ticker"]: c["sector"] for c in COMPANIES}
NAME_BY_TICKER: dict[str, str] = {c["ticker"]: c["name"] for c in COMPANIES}
