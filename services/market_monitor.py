"""FinanceBro - Ad-hoc Market Event Monitor.

Intraday-Überwachung auf dramatische Marktbewegungen:
  - Portfolio-Crash / Rally (≥2% Gesamtveränderung)
  - Einzelaktien-Extreme (≤-5% Crash, ≥+8% Spike)
  - Fear & Greed Shift (≥15 Punkte Veränderung zum Vortag)
  - Automatische Telegram-Alerts mit AI-Kontext (Gemini Flash)

Wird alle 30 Min (Mo-Fr 9-22 Uhr) vom Scheduler aufgerufen.
Deduplizierung verhindert Alert-Spam (max 1 Alert pro Event pro Tag).
"""
import json
import logging
from datetime import date, datetime
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Konfiguration (Schwellenwerte)
# ─────────────────────────────────────────────────────────────

# Portfolio-Level
PORTFOLIO_CRASH_THRESHOLD = -2.0   # % → Alert bei ≤ -2%
PORTFOLIO_RALLY_THRESHOLD = 3.0    # % → Alert bei ≥ +3%

# Einzelaktien
STOCK_CRASH_THRESHOLD = -5.0       # % → Alert bei ≤ -5% intraday
STOCK_SPIKE_THRESHOLD = 8.0        # % → Alert bei ≥ +8% intraday

# Fear & Greed
FEAR_GREED_SHIFT_THRESHOLD = 15    # Punkte → Alert bei ≥ 15 Shift
FEAR_GREED_EXTREME_LOW = 20        # ≤ 20 = Extreme Fear → Alert

# Rate Limiting
MAX_ALERTS_PER_DAY = 8

# ─────────────────────────────────────────────────────────────
# State (In-Memory, täglicher Reset)
# ─────────────────────────────────────────────────────────────

_sent_events: set[str] = set()        # Dedup: "event_type:ticker:date"
_alert_count: int = 0
_state_date: Optional[date] = None
_last_fear_greed: Optional[int] = None  # Letzter bekannter F&G-Wert


def _reset_daily():
    """Reset State bei Tageswechsel."""
    global _sent_events, _alert_count, _state_date
    today = date.today()
    if _state_date != today:
        _sent_events = set()
        _alert_count = 0
        _state_date = today


def _is_duplicate(event_key: str) -> bool:
    """Prüft ob ein Event heute bereits gesendet wurde."""
    return event_key in _sent_events


def _mark_sent(event_key: str):
    """Markiert ein Event als gesendet."""
    global _alert_count
    _sent_events.add(event_key)
    _alert_count += 1


# ─────────────────────────────────────────────────────────────
# Haupt-Entry-Point
# ─────────────────────────────────────────────────────────────

async def check_market_events(force: bool = False) -> dict:
    """Prüft auf dramatische Marktbewegungen und sendet Alerts.

    Args:
        force: Wenn True, Deduplizierung überspringen

    Returns:
        dict mit "events_detected" (int), "alerts_sent" (int), "events" (list)
    """
    global _last_fear_greed
    _reset_daily()

    if not settings.telegram_configured:
        logger.debug("Market Monitor übersprungen (Telegram nicht konfiguriert)")
        return {"events_detected": 0, "alerts_sent": 0, "events": []}

    # Rate Limiting
    if not force and _alert_count >= MAX_ALERTS_PER_DAY:
        logger.debug(f"Market Monitor: Tägliches Alert-Limit ({MAX_ALERTS_PER_DAY}) erreicht")
        return {"events_detected": 0, "alerts_sent": 0, "events": []}

    # Portfolio-Daten holen
    from state import portfolio_data
    summary = portfolio_data.get("summary")
    if not summary or not summary.stocks:
        logger.debug("Market Monitor: Keine Portfolio-Daten")
        return {"events_detected": 0, "alerts_sent": 0, "events": []}

    events = []

    # 1. Portfolio-Level Events
    portfolio_events = _detect_portfolio_events(summary)
    events.extend(portfolio_events)

    # 2. Einzelaktien Events
    stock_events = _detect_single_stock_events(summary.stocks)
    events.extend(stock_events)

    # 3. Fear & Greed Events
    fg_events = _detect_fear_greed_events(summary)
    events.extend(fg_events)

    # Aktualisiere letzten F&G-Wert für nächsten Check
    if summary.fear_greed:
        _last_fear_greed = summary.fear_greed.value

    if not events:
        logger.debug("Market Monitor: Keine Events erkannt")
        return {"events_detected": 0, "alerts_sent": 0, "events": []}

    # Deduplizieren
    new_events = []
    for event in events:
        if force or not _is_duplicate(event["key"]):
            new_events.append(event)

    if not new_events:
        logger.debug("Market Monitor: Alle Events bereits gesendet (Duplikate)")
        return {"events_detected": len(events), "alerts_sent": 0, "events": []}

    # AI-Kontext für die wichtigsten Events holen
    if settings.gemini_configured:
        try:
            ai_context = await _get_event_context(new_events, summary)
        except Exception as e:
            logger.warning(f"Market Monitor AI-Kontext fehlgeschlagen: {e}")
            ai_context = ""
    else:
        ai_context = ""

    # Telegram-Alert senden
    message = _format_market_alert(new_events, ai_context, summary)
    from services.telegram import send_message
    success = await send_message(message)

    if success:
        for event in new_events:
            _mark_sent(event["key"])
        logger.info(f"🚨 Market Monitor: {len(new_events)} Events gesendet")
    else:
        logger.error("Market Monitor: Alert-Versand fehlgeschlagen")

    return {
        "events_detected": len(events),
        "alerts_sent": len(new_events) if success else 0,
        "events": [
            {"type": e["type"], "ticker": e.get("ticker", ""), "value": e["value"]}
            for e in new_events
        ],
    }


# ─────────────────────────────────────────────────────────────
# Event-Detection
# ─────────────────────────────────────────────────────────────

def _detect_portfolio_events(summary) -> list[dict]:
    """Erkennt Portfolio-Level Events (Gesamtveränderung)."""
    events = []
    daily_pct = summary.daily_total_change_pct

    if daily_pct is None or daily_pct == 0:
        return events

    today = date.today().isoformat()

    if daily_pct <= PORTFOLIO_CRASH_THRESHOLD:
        events.append({
            "type": "portfolio_crash",
            "key": f"portfolio_crash:{today}",
            "value": daily_pct,
            "emoji": "🔴📉",
            "title": "Portfolio-Crash",
            "description": (
                f"Dein Portfolio verliert heute {daily_pct:+.1f}% "
                f"({summary.daily_total_change:+,.0f} EUR)"
            ),
        })
    elif daily_pct >= PORTFOLIO_RALLY_THRESHOLD:
        events.append({
            "type": "portfolio_rally",
            "key": f"portfolio_rally:{today}",
            "value": daily_pct,
            "emoji": "🟢🚀",
            "title": "Portfolio-Rally",
            "description": (
                f"Dein Portfolio steigt heute {daily_pct:+.1f}% "
                f"({summary.daily_total_change:+,.0f} EUR)"
            ),
        })

    return events


def _detect_single_stock_events(stocks) -> list[dict]:
    """Erkennt extreme Einzelaktien-Bewegungen."""
    events = []
    today = date.today().isoformat()

    for stock in stocks:
        ticker = stock.position.ticker
        if ticker == "CASH":
            continue

        daily_pct = stock.position.daily_change_pct
        if daily_pct is None or daily_pct == 0:
            continue

        if daily_pct <= STOCK_CRASH_THRESHOLD:
            # Gewicht im Portfolio berechnen
            weight = stock.position.weight_percent if hasattr(stock.position, 'weight_percent') else 0
            events.append({
                "type": "stock_crash",
                "key": f"stock_crash:{ticker}:{today}",
                "ticker": ticker,
                "value": daily_pct,
                "emoji": "🔴💥",
                "title": f"{ticker} Crash",
                "description": (
                    f"{stock.position.name} ({ticker}) stürzt ab: "
                    f"{daily_pct:+.1f}% heute"
                ),
            })
        elif daily_pct >= STOCK_SPIKE_THRESHOLD:
            events.append({
                "type": "stock_spike",
                "key": f"stock_spike:{ticker}:{today}",
                "ticker": ticker,
                "value": daily_pct,
                "emoji": "🟢⚡",
                "title": f"{ticker} Spike",
                "description": (
                    f"{stock.position.name} ({ticker}) explodiert: "
                    f"{daily_pct:+.1f}% heute"
                ),
            })

    # Sortiere: größte Crashes zuerst, dann größte Spikes
    events.sort(key=lambda e: abs(e["value"]), reverse=True)
    return events[:5]  # Max 5 Einzelaktien-Events


def _detect_fear_greed_events(summary) -> list[dict]:
    """Erkennt dramatische Veränderungen im Fear & Greed Index."""
    global _last_fear_greed
    events = []

    if not summary.fear_greed:
        return events

    current_fg = summary.fear_greed.value
    fg_label = summary.fear_greed.label
    today = date.today().isoformat()

    # Extreme Fear Alert
    if current_fg <= FEAR_GREED_EXTREME_LOW:
        events.append({
            "type": "extreme_fear",
            "key": f"extreme_fear:{today}",
            "value": current_fg,
            "emoji": "😱",
            "title": "Extreme Fear",
            "description": (
                f"Fear & Greed Index bei {current_fg}/100 ({fg_label}) — "
                f"historisch oft ein Kaufsignal"
            ),
        })

    # Shift-Alert (wenn Vortags-Wert bekannt)
    if _last_fear_greed is not None:
        shift = current_fg - _last_fear_greed
        if abs(shift) >= FEAR_GREED_SHIFT_THRESHOLD:
            direction = "gestiegen" if shift > 0 else "gefallen"
            events.append({
                "type": "fear_greed_shift",
                "key": f"fg_shift:{today}",
                "value": shift,
                "emoji": "📊🔀",
                "title": "Marktstimmung dreht sich",
                "description": (
                    f"Fear & Greed Index um {abs(shift)} Punkte {direction}: "
                    f"{_last_fear_greed} → {current_fg} ({fg_label})"
                ),
            })

    return events


# ─────────────────────────────────────────────────────────────
# AI-Kontext (Gemini Flash)
# ─────────────────────────────────────────────────────────────

async def _get_event_context(events: list[dict], summary) -> str:
    """Holt AI-generierte Erklärung für die Events via Gemini Flash.

    Args:
        events: Liste der erkannten Events
        summary: Portfolio-Zusammenfassung

    Returns:
        Kurzer AI-Kontext (max 400 Zeichen)
    """
    from services.vertex_ai import get_client, get_grounded_config

    client = get_client()

    # Event-Beschreibung aufbauen
    event_lines = []
    for e in events[:3]:  # Max 3 Events für Kontext
        event_lines.append(f"- {e['title']}: {e['description']}")

    tickers_mentioned = [e.get("ticker", "") for e in events if e.get("ticker")]
    ticker_str = ", ".join(tickers_mentioned) if tickers_mentioned else "Gesamtmarkt"

    today_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    prompt = (
        f"Datum/Zeit: {today_str}\n\n"
        f"Folgende Market Events wurden erkannt:\n"
        + "\n".join(event_lines) + "\n\n"
        f"Portfolio-Wert: {summary.total_value:,.0f} EUR\n"
        f"Betroffene Ticker: {ticker_str}\n\n"
        "Erkläre in max 300 Zeichen auf Deutsch:\n"
        "1. Was passiert gerade am Markt? (möglicher Auslöser)\n"
        "2. Was sollte der Anleger jetzt beachten?\n\n"
        "Nutze aktuelle Nachrichten via Google Search. "
        "Sei konkret, nicht generisch. Kein Markdown, nur Plain Text mit Emojis."
    )

    try:
        config = get_grounded_config()
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=config,
        )
        return response.text.strip() if response.text else ""
    except Exception as e:
        logger.warning(f"Market Monitor AI-Kontext: {e}")
        return ""


# ─────────────────────────────────────────────────────────────
# Telegram-Formatierung
# ─────────────────────────────────────────────────────────────

def _format_market_alert(events: list[dict], ai_context: str, summary) -> str:
    """Formatiert Market Events als Telegram-Nachricht.

    Args:
        events: Liste der neuen Events
        ai_context: AI-generierter Kontext
        summary: Portfolio-Zusammenfassung

    Returns:
        Formatierter Telegram-Text
    """
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    severity = _get_severity(events)

    lines = [
        f"🚨 *FinanceBro Market Alert* {severity}",
        f"_{now}_",
        "",
    ]

    # Events auflisten
    for event in events:
        lines.append(f"{event['emoji']} *{event['title']}*")
        lines.append(f"  {event['description']}")
        lines.append("")

    # Portfolio-Kontext
    if summary.daily_total_change != 0:
        day_emoji = "🟢" if summary.daily_total_change >= 0 else "🔴"
        lines.append(
            f"💰 Portfolio: {summary.total_value:,.0f} EUR "
            f"({day_emoji} {summary.daily_total_change:+,.0f} EUR heute)"
        )
        lines.append("")

    # AI-Kontext
    if ai_context:
        lines.append("🤖 *AI Einschätzung*")
        lines.append(ai_context)
        lines.append("")

    # Footer
    lines.append("─" * 30)
    lines.append(f"_Market Monitor • {len(events)} Event(s)_")

    return "\n".join(lines)


def _get_severity(events: list[dict]) -> str:
    """Bestimmt die Severity-Stufe basierend auf Events."""
    types = {e["type"] for e in events}

    if "portfolio_crash" in types:
        return "🔴🔴🔴"
    elif "stock_crash" in types or "extreme_fear" in types:
        return "🔴🔴"
    elif "portfolio_rally" in types or "stock_spike" in types:
        return "🟢"
    else:
        return "🟡"


# ─────────────────────────────────────────────────────────────
# Status / Info
# ─────────────────────────────────────────────────────────────

def get_monitor_status() -> dict:
    """Gibt den aktuellen Status des Market Monitors zurück."""
    _reset_daily()
    return {
        "alerts_sent_today": _alert_count,
        "max_alerts_per_day": MAX_ALERTS_PER_DAY,
        "events_sent_today": list(_sent_events),
        "last_fear_greed": _last_fear_greed,
        "thresholds": {
            "portfolio_crash": PORTFOLIO_CRASH_THRESHOLD,
            "portfolio_rally": PORTFOLIO_RALLY_THRESHOLD,
            "stock_crash": STOCK_CRASH_THRESHOLD,
            "stock_spike": STOCK_SPIKE_THRESHOLD,
            "fear_greed_shift": FEAR_GREED_SHIFT_THRESHOLD,
            "fear_greed_extreme_low": FEAR_GREED_EXTREME_LOW,
        },
    }
