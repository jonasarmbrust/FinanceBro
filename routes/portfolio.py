"""FinanzBro - Portfolio & Daten API-Routes.

GET-Endpoints für Dashboard, Portfolio, Aktien, Rebalancing, etc.
"""
import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

from state import portfolio_data
from config import settings
from models import SectorAllocation

logger = logging.getLogger(__name__)

router = APIRouter()

STATIC_DIR = Path(__file__).parent.parent / "static"


@router.get("/")
async def index():
    """Serve the dashboard."""
    html_file = STATIC_DIR / "index.html"
    if html_file.exists():
        return FileResponse(str(html_file))
    return JSONResponse({"error": "Dashboard nicht gefunden"}, status_code=404)


@router.get("/api/portfolio")
async def get_portfolio():
    """Portfolio-Übersicht mit Scores."""
    summary = portfolio_data.get("summary")
    if not summary:
        return JSONResponse({"error": "Daten werden geladen...", "refreshing": True}, status_code=503)
    return summary.model_dump()


@router.get("/api/stock/{ticker}")
async def get_stock(ticker: str):
    """Detaildaten einer einzelnen Aktie."""
    summary = portfolio_data.get("summary")
    if not summary:
        return JSONResponse({"error": "Daten werden geladen..."}, status_code=503)

    for stock in summary.stocks:
        if stock.position.ticker.upper() == ticker.upper():
            return stock.model_dump()

    return JSONResponse({"error": f"Aktie {ticker} nicht im Portfolio"}, status_code=404)


@router.get("/api/stock/{ticker}/history")
async def get_stock_history(ticker: str, period: str = "3month"):
    """Historische Kursdaten für eine Aktie."""
    if period not in ("1month", "3month", "6month", "1year"):
        period = "3month"

    if settings.demo_mode:
        # Generate synthetic demo data
        import random
        from datetime import timedelta as td
        days = {"1month": 30, "3month": 90, "6month": 180, "1year": 365}.get(period, 90)
        base_price = 150.0
        data = []
        for i in range(days):
            date = (datetime.now() - td(days=days - i)).strftime("%Y-%m-%d")
            base_price *= (1 + random.uniform(-0.03, 0.035))
            data.append({"date": date, "close": round(base_price, 2)})
        return data

    from fetchers.fmp import get_historical_prices
    return await get_historical_prices(ticker, period)


@router.get("/api/portfolio/history")
async def get_portfolio_history(days: int = 90):
    """Portfolio-Verlauf: Investiertes Kapital + aktueller Wert ueber Zeit.

    Datenquellen (in Prioritaet):
    1. Parqet Activities -> rekonstruierte Investment-Timeline
    2. Lokale Snapshots aus vorherigen Refreshes
    3. Aktueller Portfoliowert als einzelner Datenpunkt
    """
    # --- 1. Versuche Investment-Timeline aus Parqet Activities ---
    try:
        # Activities aus State lesen (bereits beim Refresh gecacht)
        activities = portfolio_data.get("activities")
        if not activities:
            from fetchers.parqet import fetch_portfolio_activities_raw
            activities = await fetch_portfolio_activities_raw()
        from datetime import datetime as dt, timedelta
        if activities and len(activities) > 0:
            # Kumuliertes investiertes Kapital pro Tag berechnen
            daily_invested = {}
            cumulative = 0.0

            for act in activities:
                date = act.get("date", "")
                if not date:
                    continue
                act_type = act.get("type", "")
                amount = act.get("amount", 0)

                if act_type in ("buy", "kauf", "purchase"):
                    cumulative += amount
                elif act_type in ("sell", "verkauf", "sale"):
                    cumulative -= amount
                elif act_type in ("transferin", "transfer_in"):
                    cumulative += amount
                elif act_type in ("transferout", "transfer_out"):
                    cumulative -= amount

                daily_invested[date] = round(cumulative, 2)

            if daily_invested:
                # Cutoff anwenden
                if days < 9999:
                    cutoff = (dt.now() - timedelta(days=days)).strftime("%Y-%m-%d")
                    filtered = {d: v for d, v in daily_invested.items() if d >= cutoff}
                else:
                    filtered = daily_invested

                if filtered:
                    # Aktuellen Portfoliowert als letzten Datenpunkt hinzufuegen
                    summary = portfolio_data.get("summary")
                    current_value = summary.total_value if summary else 0
                    today = dt.now().strftime("%Y-%m-%d")

                    result = [
                        {"date": d, "total_value": 0, "invested_capital": v}
                        for d, v in sorted(filtered.items())
                    ]
                    # Aktuellen Wert beim letzten Eintrag setzen
                    if result and current_value > 0:
                        result[-1]["total_value"] = round(current_value, 2)

                    return result

    except Exception as e:
        logger.warning(f"Portfolio Activities Timeline fehlgeschlagen: {e}")

    # --- 2. Fallback: Lokale Snapshots ---
    from engine.history import load_history
    local = load_history(days=days)
    if local:
        return local

    # --- 3. Fallback: Aktueller Portfoliowert ---
    summary = portfolio_data.get("summary")
    if summary and summary.total_value > 0:
        from datetime import datetime as dt
        return [{
            "date": dt.now().strftime("%Y-%m-%d"),
            "total_value": round(summary.total_value, 2),
            "invested_capital": round(summary.total_cost, 2),
        }]

    return []


@router.get("/api/portfolio/activities")
async def get_portfolio_activities():
    """Alle Kauf/Verkauf/Dividenden-Transaktionen von Parqet."""
    try:
        from fetchers.parqet import fetch_portfolio_activities_raw
        return await fetch_portfolio_activities_raw()
    except Exception as e:
        logger.error(f"Portfolio Activities Fehler: {e}")
        return []


@router.get("/api/rebalancing")
async def get_rebalancing():
    """Rebalancing-Empfehlungen."""
    summary = portfolio_data.get("summary")
    if not summary or not summary.rebalancing:
        return JSONResponse({"error": "Keine Rebalancing-Daten"}, status_code=503)
    return summary.rebalancing.model_dump()


@router.get("/api/tech-picks")
async def get_tech_picks():
    """Tägliche Tech-Empfehlungen."""
    summary = portfolio_data.get("summary")
    if not summary:
        return JSONResponse({"error": "Daten werden geladen..."}, status_code=503)
    return [p.model_dump() for p in summary.tech_picks]


@router.get("/api/sectors")
async def get_sectors():
    """Sektor-Allokation."""
    summary = portfolio_data.get("summary")
    if not summary:
        return JSONResponse({"error": "Daten werden geladen..."}, status_code=503)

    sectors: dict[str, SectorAllocation] = {}
    total_value = summary.total_value

    for s in summary.stocks:
        sector = s.position.sector or "Unknown"
        if sector not in sectors:
            sectors[sector] = SectorAllocation(sector=sector)
        sa = sectors[sector]
        sa.value += s.position.current_value
        sa.count += 1

    for sa in sectors.values():
        sa.weight = round((sa.value / total_value * 100) if total_value > 0 else 0, 1)
        sa.value = round(sa.value, 2)

    return [sa.model_dump() for sa in sorted(sectors.values(), key=lambda x: x.value, reverse=True)]


@router.get("/api/fear-greed")
async def get_fear_greed():
    """Fear & Greed Index."""
    summary = portfolio_data.get("summary")
    if not summary or not summary.fear_greed:
        return {"value": 50, "label": "Neutral", "source": "N/A"}
    return summary.fear_greed.model_dump()


@router.get("/api/status")
async def get_status():
    """App-Status."""
    from fetchers.fmp import get_fmp_usage
    return {
        "status": "ok",
        "demo_mode": settings.demo_mode,
        "last_refresh": portfolio_data.get("last_refresh"),
        "refreshing": portfolio_data["refreshing"],
        "positions": portfolio_data["summary"].num_positions if portfolio_data["summary"] else 0,
        "ws_connected": _is_ws_connected(),
        "fmp_usage": get_fmp_usage(),
    }


@router.get("/api/earnings-calendar")
async def get_earnings_calendar():
    """Earnings-Kalender: Anstehende Earnings-Termine der Portfolio-Positionen."""
    summary = portfolio_data.get("summary")
    if not summary or not summary.stocks:
        return {"earnings": [], "message": "Keine Portfolio-Daten"}

    earnings = []
    for stock in summary.stocks:
        if stock.position.ticker == "CASH":
            continue
        if stock.yfinance and stock.yfinance.next_earnings_date:
            entry = {
                "ticker": stock.position.ticker,
                "name": stock.position.name,
                "date": stock.yfinance.next_earnings_date,
                "beat_rate": stock.yfinance.earnings_beat_rate,
                "surprise_avg": stock.yfinance.earnings_surprise_avg,
            }
            earnings.append(entry)

    # Sortieren nach Datum (nächster zuerst)
    earnings.sort(key=lambda x: x["date"])

    return {
        "earnings": earnings,
        "count": len(earnings),
    }


def _is_ws_connected() -> bool:
    """Prüft ob yFinance WebSocket verbunden ist."""
    try:
        from fetchers.yfinance_ws import get_yf_streamer
        return get_yf_streamer().is_connected
    except Exception:
        return False

