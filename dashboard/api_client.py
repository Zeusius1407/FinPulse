"""Thin client the Streamlit dashboard uses to talk to the FinPulse REST API.

The dashboard deliberately consumes the *API* (not the DB directly) so the
project demonstrates the full request flow: Dashboard -> REST API -> DB.
Set FINPULSE_API_URL to point at a deployed API; defaults to localhost.
"""
from __future__ import annotations

import os

import requests

API_URL = os.getenv("FINPULSE_API_URL", "http://127.0.0.1:8000").rstrip("/")
TIMEOUT = 20


class APIError(RuntimeError):
    pass


def _get(path: str, params: dict | None = None):
    url = f"{API_URL}{path}"
    try:
        r = requests.get(url, params=params, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise APIError(f"Could not reach the API at {API_URL}. Is it running?\n{exc}")
    if r.status_code != 200:
        raise APIError(f"{r.status_code} from {path}: {r.text[:200]}")
    return r.json()


def get_stocks(sort_by: str = "market_cap", order: str = "desc", limit: int = 100):
    return _get("/stocks", {"sort_by": sort_by, "order": order, "limit": limit})


def get_stock(ticker: str):
    return _get(f"/stocks/{ticker}")


def get_history(ticker: str, period: str = "1y"):
    return _get(f"/stocks/{ticker}/history", {"period": period})


def get_market_summary():
    return _get("/market-summary")


def get_sectors():
    return _get("/sectors")


def compare(tickers: list[str]):
    return _get("/compare", {"tickers": ",".join(tickers)})


def base_url() -> str:
    return API_URL
