"""FinanzBro - Refresh API-Routes.

POST-Endpoints zum Auslösen von Daten-Refreshes.
"""
import asyncio
import logging

from fastapi import APIRouter

from state import portfolio_data, refresh_progress
from config import settings
from services.refresh import _refresh_data, _quick_price_refresh, _update_parqet

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/refresh/status")
async def get_refresh_status():
    """Aktueller Refresh-Status für UI-Polling."""
    return {
        "refreshing": portfolio_data["refreshing"],
        "step": refresh_progress["step"],
        "percent": refresh_progress["percent"],
        "started_at": refresh_progress["started_at"],
        "last_refresh": portfolio_data.get("last_refresh"),
    }


@router.post("/api/refresh")
async def trigger_refresh():
    """Kompletter Refresh: Portfolio + Finanzdaten."""
    if portfolio_data["refreshing"]:
        return {"status": "already_refreshing", "message": "Refresh läuft bereits..."}

    portfolio_data["refreshing"] = True  # SOFORT setzen, BEVOR Task startet
    asyncio.create_task(_refresh_data())
    return {"status": "started", "message": "Kompletter Refresh gestartet!"}


@router.post("/api/refresh/prices")
async def trigger_price_refresh():
    """Schneller Kurs-Update via yfinance (für Cloud Scheduler)."""
    summary = portfolio_data.get("summary")
    if not summary or not summary.stocks:
        # Kein Portfolio geladen -> vollen Refresh starten
        asyncio.create_task(_refresh_data())
        return {"status": "full_refresh", "message": "Kein Portfolio - starte vollen Refresh"}

    await _quick_price_refresh()
    return {"status": "ok", "message": f"Kurse aktualisiert für {summary.num_positions} Positionen"}


@router.post("/api/refresh/portfolio")
async def trigger_portfolio_refresh():
    """Nur Parqet-Portfolio neu laden (Cache löschen)."""
    if portfolio_data["refreshing"]:
        return {"status": "already_refreshing", "message": "Refresh läuft bereits..."}

    # Clear Parqet cache to force re-fetch
    try:
        from fetchers.parqet import clear_cache as clear_parqet_cache
        clear_parqet_cache()
        logger.info("🗑️ Parqet-Cache gelöscht")
    except Exception as e:
        logger.warning(f"Cache-Clear fehlgeschlagen: {e}")

    portfolio_data["refreshing"] = True  # SOFORT setzen
    asyncio.create_task(_refresh_data())
    return {"status": "started", "message": "Portfolio-Abgleich gestartet!"}


@router.post("/api/refresh/parqet")
async def trigger_parqet_update():
    """Update Parqet: Positionen + aktuelle Kurse (schnell, ~10s)."""
    if portfolio_data["refreshing"]:
        return {"status": "already_refreshing", "message": "Update läuft bereits..."}

    # Clear Parqet cache to force fresh API fetch
    try:
        from fetchers.parqet import clear_cache as clear_parqet_cache
        clear_parqet_cache()
    except Exception:
        pass

    result = await _update_parqet()
    return result


@router.post("/api/refresh/scores")
async def trigger_scores_refresh():
    """Nur Finanzdaten neu bewerten (alle Caches löschen außer Portfolio)."""
    if portfolio_data["refreshing"]:
        return {"status": "already_refreshing", "message": "Refresh läuft bereits..."}

    # Clear financial data caches
    cache_dir = settings.CACHE_DIR
    cleared = 0
    for f in cache_dir.glob("*.json"):
        if f.name not in ("parqet_cache.json", "parqet_tokens.json", "portfolio_history.json"):
            f.unlink()
            cleared += 1
    logger.info(f"🗑️ {cleared} Finanzdaten-Caches gelöscht")

    portfolio_data["refreshing"] = True  # SOFORT setzen
    asyncio.create_task(_refresh_data())
    return {"status": "started", "message": f"Neubewertung gestartet ({cleared} Caches gelöscht)!"}
