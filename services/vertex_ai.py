"""FinanzBro - Vertex AI Service.

Zentrales Modul für Google Gemini / Vertex AI:
  - Client-Erstellung (Vertex AI mit Service Account ODER API Key Fallback)
  - Google Search Grounding für Echtzeit-Marktdaten
  - Context Caching für Portfolio-Kontext (Kostenoptimierung)

Bevorzugt Vertex AI (auf Cloud Run), fällt auf API Key zurück (lokal).
"""
import logging
from datetime import date
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)

# Globaler Cache-Name (wird nach Refresh gesetzt)
_active_cache_name: Optional[str] = None

# Tägliches AI-Call-Limit (Kostenschutz)
_MAX_DAILY_CALLS = 100
_daily_call_count = 0
_daily_call_date: Optional[date] = None


def _check_daily_limit():
    """Prüft und aktualisiert das tägliche AI-Call-Limit.

    Verhindert unkontrollierte Kosten durch Bugs, Spam oder Fehlfunktionen.
    Limit resettet sich um Mitternacht automatisch.
    """
    global _daily_call_count, _daily_call_date

    today = date.today()
    if _daily_call_date != today:
        _daily_call_count = 0
        _daily_call_date = today

    _daily_call_count += 1

    if _daily_call_count > _MAX_DAILY_CALLS:
        raise RuntimeError(
            f"Tägliches AI-Call-Limit erreicht ({_MAX_DAILY_CALLS}/Tag). "
            "Schutz gegen unkontrollierte Kosten. Resettet um Mitternacht."
        )

    if _daily_call_count % 10 == 0:
        logger.info(f"📊 AI-Calls heute: {_daily_call_count}/{_MAX_DAILY_CALLS}")


def get_client():
    """Erstellt einen Google GenAI Client (mit täglichem Call-Limit).

    Priorität:
      1. Vertex AI (wenn GCP_PROJECT_ID gesetzt → Cloud Run mit Service Account)
      2. API Key Fallback (für lokale Entwicklung)

    Raises:
        RuntimeError: Wenn tägliches Limit überschritten oder keine Config.
    """
    _check_daily_limit()

    from google import genai

    if settings.vertex_ai_configured:
        logger.debug(f"Vertex AI Client: project={settings.GCP_PROJECT_ID}, location={settings.GCP_LOCATION}")
        return genai.Client(
            vertexai=True,
            project=settings.GCP_PROJECT_ID,
            location=settings.GCP_LOCATION,
        )
    elif settings.GEMINI_API_KEY:
        logger.debug("API Key Client (Fallback)")
        return genai.Client(api_key=settings.GEMINI_API_KEY)
    else:
        raise RuntimeError("Weder Vertex AI noch Gemini API Key konfiguriert")


def get_daily_usage() -> dict:
    """Gibt aktuelle AI-Call-Statistik zurück."""
    return {
        "calls_today": _daily_call_count,
        "max_daily": _MAX_DAILY_CALLS,
        "remaining": max(0, _MAX_DAILY_CALLS - _daily_call_count),
        "date": str(_daily_call_date or date.today()),
    }


def get_grounded_config() -> dict:
    """Erstellt eine Config mit Google Search Grounding.

    Gemini sucht automatisch im Web nach aktuellen Infos,
    bevor es antwortet → echte Marktdaten statt Halluzinationen.
    """
    from google.genai.types import Tool, GoogleSearch

    return {
        "tools": [Tool(google_search=GoogleSearch())],
    }


async def cache_portfolio_context(summary) -> Optional[str]:
    """Cached den Portfolio-Kontext für alle AI-Services.

    Wird nach jedem Refresh aufgerufen. Spart ~75% Input-Token-Kosten
    bei mehreren AI-Calls mit gleichem Portfolio-Kontext.

    Returns:
        Cache-Name oder None bei Fehler
    """
    global _active_cache_name

    if not settings.vertex_ai_configured:
        logger.debug("Context Caching nur mit Vertex AI verfügbar")
        return None

    try:
        client = get_client()

        # Portfolio-Kontext aufbauen
        context_lines = [
            "Du bist ein professioneller Finanzanalyst. "
            "Hier ist der aktuelle Portfolio-Status:",
            "",
            f"Portfolio-Wert: {summary.total_value:,.0f} EUR",
            f"P&L: {summary.total_pnl:+,.0f} EUR ({summary.total_pnl_percent:+.1f}%)",
            f"Positionen: {summary.num_positions}",
        ]

        if summary.fear_greed:
            context_lines.append(
                f"Fear & Greed Index: {summary.fear_greed.value}/100 "
                f"({summary.fear_greed.label})"
            )

        context_lines.append("")
        context_lines.append("Positionen (Ticker | Name | Score | Rating | P&L% | Sektor):")

        for stock in summary.stocks:
            if stock.position.ticker == "CASH":
                continue
            score_val = stock.score.total_score if stock.score else 0
            rating_val = stock.score.rating.value if stock.score else "hold"
            pnl_pct = stock.position.pnl_percent
            sector = stock.position.sector
            context_lines.append(
                f"  {stock.position.ticker} ({stock.position.name}) | "
                f"Score: {score_val:.0f} | {rating_val} | P&L: {pnl_pct:+.1f}% | {sector}"
            )

        context_text = "\n".join(context_lines)

        # Alten Cache löschen (falls vorhanden)
        if _active_cache_name:
            try:
                await client.aio.caches.delete(name=_active_cache_name)
                logger.debug(f"Alter Cache gelöscht: {_active_cache_name}")
            except Exception:
                pass  # Cache existiert evtl. nicht mehr (TTL abgelaufen)

        # Neuen Cache erstellen
        from google.genai.types import Content, Part

        import asyncio
        cache = await asyncio.wait_for(
            client.aio.caches.create(
                model="gemini-2.5-pro",
                config={
                    "contents": [
                        Content(
                            role="user",
                            parts=[Part(text=context_text)],
                        )
                    ],
                    "display_name": "finanzbro-portfolio",
                    "ttl": "14400s",  # 4 Stunden (bis zum nächsten Refresh)
                },
            ),
            timeout=20.0
        )

        _active_cache_name = cache.name
        logger.info(f"💾 Portfolio-Kontext gecached: {cache.name} (TTL: 4h)")
        return cache.name

    except Exception as e:
        logger.warning(f"Context Caching fehlgeschlagen (nicht kritisch): {e}")
        _active_cache_name = None
        return None


def get_cached_content() -> Optional[str]:
    """Gibt den aktiven Cache-Namen zurück (oder None)."""
    return _active_cache_name
