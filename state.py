"""FinanceBro - Zentraler gemeinsamer Zustand.

Dieses Modul enthält den globalen State, der von Services und Routes
geteilt wird. Durch die Zentralisierung wird vermieden, dass mehrere
Module inkompatible Kopien derselben Daten halten.
"""
import asyncio
from typing import Optional
from zoneinfo import ZoneInfo


# Timezone für konsistente Zeitstempel (Cloud Run UTC vs. lokal CET)
TZ_BERLIN = ZoneInfo("Europe/Berlin")

# Zentrale yFinance-Ticker-Aliases
# (Nur Ticker die in yFinance anders heißen als im Portfolio)
# Die meisten DE-Ticker haben bereits .DE-Suffix aus der ISIN_TICKER_MAP
YFINANCE_ALIASES = {
    "DTEGY": "DTE.DE",     # Deutsche Telekom US-ADR → Frankfurt
}

# Global data store (refreshed periodically)
portfolio_data: dict = {
    "summary": None,
    "last_refresh": None,
    "refreshing": False,
    "activities": None,  # Cached Parqet activities (list[dict])
}

# Refresh-Fortschritt (für UI-Feedback)
refresh_progress: dict = {
    "step": "",           # Aktueller Schritt (z.B. "Lade FMP-Daten...")
    "percent": 0,         # 0-100
    "started_at": None,   # ISO timestamp
}

# Lock um parallele Refreshes zu verhindern
refresh_lock = asyncio.Lock()


# ─── Typed Accessors ────────────────────────────────────────
# Bevorzuge diese Funktionen gegenüber direktem dict-Zugriff.

def get_summary() -> Optional["PortfolioSummary"]:  # noqa: F821
    """Read-only Zugriff auf das aktuelle PortfolioSummary."""
    return portfolio_data.get("summary")


def set_summary(summary) -> None:
    """Setzt das PortfolioSummary (nur aus Refresh-Pipeline aufrufen)."""
    portfolio_data["summary"] = summary


def is_refreshing() -> bool:
    """Prüft ob gerade ein Refresh läuft."""
    return portfolio_data.get("refreshing", False)


def set_refreshing(state: bool) -> None:
    """Setzt den Refresh-Status."""
    portfolio_data["refreshing"] = state
