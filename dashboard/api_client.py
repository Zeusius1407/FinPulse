"""Thin client the Streamlit dashboard uses to talk to the FinPulse REST API.

The dashboard deliberately consumes the *API* (not the DB directly) so the
project demonstrates the full request flow: Dashboard -> REST API -> DB.

The API URL is resolved in this order:
  1. Streamlit secret  FINPULSE_API_URL   (set in the app's Secrets on Cloud)
  2. environment var   FINPULSE_API_URL   (for local / other hosts)
  3. http://127.0.0.1:8000                (local default)
"""
from __future__ import annotations

import os

import requests


def _resolve_api_url() -> str:
    # 1) Streamlit Cloud secret (works even if it isn't exported as an env var).
    try:
        import streamlit as st

        val = st.secrets.get("FINPULSE_API_URL")
        if val:
            return str(val).rstrip("/")
    except Exception:
        pass  # no secrets file / not running under Streamlit
    # 2) environment variable, 3) local default
    return os.getenv("FINPULSE_API_URL", "http://127.0.0.1:8000").rstrip("/")


API_URL = _resolve_api_url()
TIMEOUT = 30  # Render free tier can cold-start (~30-60s) after idling


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