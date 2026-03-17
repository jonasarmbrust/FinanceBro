"""FinanzBro - AI Finance Agent.

Täglicher Analyse-Agent der:
  1. Portfolio-Daten und Analyse-Report sammelt
  2. Optional per Google Gemini AI-Research durchführt
  3. Einen strukturierten Report an Telegram sendet

Fallback: Ohne Gemini-Key wird ein rein datenbasierter Report erstellt.
"""
import logging
from datetime import datetime
from typing import Optional

from config import settings
from models import (
    AnalysisReport,
    PortfolioSummary,
    Rating,
    StockFullData,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Haupt-Entry-Point
# ─────────────────────────────────────────────────────────────

async def run_daily_report():
    """Führt den täglichen AI-Agent-Zyklus aus.

    1. Portfolio-Daten laden
    2. Analyse-Report holen/erstellen
    3. AI-Research (optional)
    4. Telegram-Report senden
    """
    from state import portfolio_data
    from services.telegram import send_message

    logger.info("🤖 AI Finance Agent startet täglichen Report...")

    if not settings.telegram_configured:
        logger.warning("Telegram nicht konfiguriert – Agent übersprungen")
        return

    # 1. Portfolio-Daten holen
    summary: Optional[PortfolioSummary] = portfolio_data.get("summary")
    if not summary or not summary.stocks:
        logger.warning("Keine Portfolio-Daten vorhanden – Agent übersprungen")
        await send_message("⚠️ FinanzBro Agent: Keine Portfolio-Daten verfügbar. Bitte zuerst einen Full-Refresh starten.")
        return

    # 2. Letzten Analyse-Report holen
    report = _get_latest_report()

    # 3. AI-Research (wenn Gemini konfiguriert)
    ai_insights = ""
    if settings.gemini_configured:
        try:
            ai_insights = await _run_gemini_research(summary, report)
        except Exception as e:
            logger.error(f"Gemini-Research fehlgeschlagen: {e}")
            ai_insights = "⚠️ AI-Research nicht verfügbar"

    # 4. Report zusammenbauen und senden
    telegram_text = _build_telegram_report(summary, report, ai_insights)
    success = await send_message(telegram_text)

    if success:
        logger.info("🤖 AI Finance Agent: Täglicher Report gesendet ✅")
    else:
        logger.error("🤖 AI Finance Agent: Report-Versand fehlgeschlagen ❌")


# ─────────────────────────────────────────────────────────────
# Report-Aufbau
# ─────────────────────────────────────────────────────────────

def _build_telegram_report(
    summary: PortfolioSummary,
    report: Optional[AnalysisReport],
    ai_insights: str = "",
) -> str:
    """Baut den vollständigen Telegram-Report zusammen."""
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    sections = []

    # Header
    sections.append(f"📊 *FinanzBro Daily Report*")
    sections.append(f"📅 {now}")
    sections.append("")

    # ── Portfolio Overview ──
    sections.append("💰 *Portfolio Übersicht*")
    sections.append(f"  Gesamtwert: {summary.total_value:,.2f} EUR")
    sections.append(f"  Gesamtkosten: {summary.total_cost:,.2f} EUR")

    pnl_emoji = "📈" if summary.total_pnl >= 0 else "📉"
    sections.append(f"  {pnl_emoji} P&L: {summary.total_pnl:+,.2f} EUR ({summary.total_pnl_percent:+.1f}%)")

    if summary.daily_total_change != 0:
        day_emoji = "🟢" if summary.daily_total_change >= 0 else "🔴"
        sections.append(f"  {day_emoji} Heute: {summary.daily_total_change:+,.2f} EUR ({summary.daily_total_change_pct:+.1f}%)")

    sections.append(f"  Positionen: {summary.num_positions}")

    # Cash-Bestand
    cash_stock = next((s for s in summary.stocks if s.position.ticker == "CASH"), None)
    if cash_stock:
        sections.append(f"  💵 Cash: {cash_stock.position.current_price:,.2f} EUR")

    # Fear & Greed
    if summary.fear_greed:
        fg = summary.fear_greed
        fg_emoji = _fear_greed_emoji(fg.value)
        sections.append(f"  {fg_emoji} Fear & Greed: {fg.value}/100 ({fg.label})")

    sections.append("")

    # ── Tagesgewinner / Tagesverlierer ──
    winners, losers = _get_daily_movers(summary.stocks)
    if winners:
        sections.append("📈 *Tagesgewinner*")
        for stock, pct in winners:
            sections.append(f"  🟢 {stock.position.ticker}: {pct:+.1f}%")
        sections.append("")
    if losers:
        sections.append("📉 *Tagesverlierer*")
        for stock, pct in losers:
            sections.append(f"  🔴 {stock.position.ticker}: {pct:+.1f}%")
        sections.append("")

    # ── P&L Attribution (Sektor-Beitrag) ──
    try:
        from engine.attribution import calculate_attribution
        attr = calculate_attribution(summary.stocks)
        if attr["sectors"]:
            sections.append("🏢 *P&L nach Sektor*")
            for s in attr["sectors"][:4]:
                emoji = "🟢" if s["pnl_eur"] >= 0 else "🔴"
                sections.append(
                    f"  {emoji} {s['sector']}: {s['pnl_eur']:+,.0f} EUR"
                )
            conc = attr["concentration"]
            sections.append(
                f"  🎯 Konzentration: {conc['risk_level']} "
                f"(Top-3 = {conc['top3_pnl_share']:.0f}%)"
            )
            sections.append("")
    except Exception:
        pass

    # ── Analyse-Report Details ──
    if report:
        # Portfolio Score
        score_emoji = {"buy": "🟢", "hold": "🟡", "sell": "🔴"}[report.portfolio_rating.value]
        sections.append(f"🎯 *Portfolio Score: {report.portfolio_score:.1f}/100* {score_emoji}")
        sections.append("")

        # Top Buys
        if report.top_buys:
            sections.append("🏆 *Top Performer*")
            for pos in report.top_buys[:5]:
                rating_icon = _rating_icon(pos.rating)
                sections.append(
                    f"  {rating_icon} {pos.ticker}: {pos.score:.0f}/100"
                    f" ({pos.weight_in_portfolio:.1f}%)"
                )
            sections.append("")

        # Top Sells / Watchlist
        if report.top_sells:
            sell_positions = [p for p in report.top_sells if p.rating == Rating.SELL]
            if sell_positions:
                sections.append("⚠️ *Watchlist (SELL-Signal)*")
                for pos in sell_positions[:5]:
                    sections.append(
                        f"  🔴 {pos.ticker}: {pos.score:.0f}/100"
                        f" ({pos.weight_in_portfolio:.1f}%)"
                    )
                sections.append("")

        # Biggest Changes
        if report.biggest_changes:
            notable = [p for p in report.biggest_changes if p.score_change and abs(p.score_change) >= 2]
            if notable:
                sections.append("📈 *Größte Veränderungen*")
                for pos in notable[:5]:
                    arrow = "⬆️" if pos.score_change > 0 else "⬇️"
                    sections.append(
                        f"  {arrow} {pos.ticker}: {pos.score_change:+.1f} Punkte"
                        f" → {pos.score:.0f}/100"
                    )
                sections.append("")

        # Data Quality
        dq = report.data_quality
        total = dq.get("total", 0)
        if total > 0:
            fmp_pct = dq.get("fmp", 0) / total * 100
            tech_pct = dq.get("technical", 0) / total * 100
            sections.append(f"📡 *Datenqualität:* FMP {fmp_pct:.0f}% | Technical {tech_pct:.0f}%")
            sections.append("")

    # ── Einzel-Positionen ──
    sections.append("📋 *Alle Positionen*")
    stocks_sorted = _sort_stocks_by_score(summary.stocks)
    for stock in stocks_sorted:
        if stock.position.ticker == "CASH":
            continue
        score_val = stock.score.total_score if stock.score else 0
        rating_icon = _rating_icon(stock.score.rating) if stock.score else "⚪"
        pnl_pct = stock.position.pnl_percent
        pnl_sign = "+" if pnl_pct >= 0 else ""
        sections.append(
            f"  {rating_icon} {stock.position.ticker}"
            f" | {score_val:.0f}/100"
            f" | {pnl_sign}{pnl_pct:.1f}%"
        )
    sections.append("")

    # ── AI Research Insights ──
    if ai_insights:
        sections.append("🤖 *AI Research Insights*")
        sections.append(ai_insights)
        sections.append("")

    # ── Rebalancing ──
    if summary.rebalancing and summary.rebalancing.actions:
        actions_buy = [a for a in summary.rebalancing.actions if a.action == "Kaufen"]
        actions_sell = [a for a in summary.rebalancing.actions if a.action == "Verkaufen"]

        if actions_buy or actions_sell:
            sections.append("💡 *Rebalancing Empfehlung*")
            for a in actions_buy[:3]:
                sections.append(f"  🟢 {a.ticker}: +{a.amount_eur:.0f} EUR ({a.shares_delta:+.2f} Stk)")
            for a in actions_sell[:3]:
                sections.append(f"  🔴 {a.ticker}: {a.amount_eur:.0f} EUR ({a.shares_delta:+.2f} Stk)")
            sections.append("")

    # ── Wissen des Tages ──
    try:
        from services.knowledge_data import get_daily_tip
        tip = get_daily_tip()
        sections.append(f"🧠 *Wissen des Tages*  _{tip['category']}_")
        sections.append(f"*{tip['title']}*")
        # Kurzversion für den Daily Report (erste 200 Zeichen des Tipps)
        tip_text = tip["text"].replace("*", "").replace("_", "")
        if len(tip_text) > 200:
            tip_text = tip_text[:200].rsplit(" ", 1)[0] + "..."
        sections.append(tip_text)
        sections.append("→ `/wissen` für den vollen Tipp")
        sections.append("")
    except Exception:
        pass

    # Footer
    sections.append("─" * 30)
    sections.append("_FinanzBro AI Agent • Automatisch generiert_")

    return "\n".join(sections)


# ─────────────────────────────────────────────────────────────
# Gemini AI Research
# ─────────────────────────────────────────────────────────────

async def _run_gemini_research(
    summary: PortfolioSummary,
    report: Optional[AnalysisReport],
) -> str:
    """Führt AI-Research via Google Gemini durch.

    Sendet Portfolio-Kontext an Gemini und bekommt:
    - Marktausblick
    - Per-Stock Kommentare zu Top-Movern
    - Handlungsempfehlungen
    """
    from services.vertex_ai import get_client, get_grounded_config, get_cached_content

    client = get_client()

    # Portfolio-Kontext aufbauen
    context_lines = [
        "Du bist ein professioneller Finanzanalyst. Analysiere folgendes Portfolio und gib kurze, "
        "prägnante Insights auf Deutsch. Maximal 800 Zeichen.",
        "",
        f"Portfolio-Wert: {summary.total_value:,.0f} EUR",
        f"P&L: {summary.total_pnl:+,.0f} EUR ({summary.total_pnl_percent:+.1f}%)",
        f"Positionen: {summary.num_positions}",
    ]

    if summary.fear_greed:
        context_lines.append(f"Fear & Greed Index: {summary.fear_greed.value}/100 ({summary.fear_greed.label})")

    context_lines.append("")
    context_lines.append("Positionen (Ticker | Score | Rating | P&L%):")

    for stock in summary.stocks:
        if stock.position.ticker == "CASH":
            continue
        score_val = stock.score.total_score if stock.score else 0
        rating_val = stock.score.rating.value if stock.score else "hold"
        pnl_pct = stock.position.pnl_percent
        sector = stock.position.sector
        context_lines.append(
            f"  {stock.position.ticker} ({stock.position.name}) | "
            f"Score: {score_val:.0f} | {rating_val} | P&L: {pnl_pct:+.1f}% | Sektor: {sector}"
        )

    if report and report.biggest_changes:
        context_lines.append("")
        context_lines.append("Größte Score-Änderungen seit letzter Analyse:")
        for pos in report.biggest_changes[:5]:
            if pos.score_change:
                context_lines.append(f"  {pos.ticker}: {pos.score_change:+.1f} Punkte")

    # Tagesgewinner / Tagesverlierer als Kontext
    winners, losers = _get_daily_movers(summary.stocks)
    if winners or losers:
        context_lines.append("")
        if winners:
            context_lines.append("Tagesgewinner: " + ", ".join(
                f"{s.position.ticker} {p:+.1f}%" for s, p in winners
            ))
        if losers:
            context_lines.append("Tagesverlierer: " + ", ".join(
                f"{s.position.ticker} {p:+.1f}%" for s, p in losers
            ))

    context_lines.append("")
    context_lines.append(
        "Erstelle eine professionelle Portfolio-Analyse auf Deutsch. Strukturiere so:\n"
        "1. MARKTUMFELD: Aktuelle Marktlage und Makro-Faktoren (Zinsen, Inflation, Geopolitik)\n"
        "2. PORTFOLIO-BEWERTUNG: Stärken und Schwächen des Portfolios, Sektor-Konzentration\n"
        "3. TAGESBEWEGER: Kommentiere kurz die größten Tagesgewinner und -verlierer aus dem Portfolio\n"
        "4. TOP POSITIONEN: Kommentiere die 2-3 auffälligsten Positionen (beste, schlechteste, größte Veränderung)\n"
        "5. HANDLUNGSEMPFEHLUNG: 1-2 konkrete, umsetzbare Maßnahmen\n\n"
        "Halte dich auf max 1400 Zeichen. Kein Markdown, nur Plain Text mit Emojis."
    )

    prompt = "\n".join(context_lines)

    try:
        # Grounding + Context Cache für bessere Ergebnisse
        config = get_grounded_config()
        cached = get_cached_content()
        if cached:
            config["cached_content"] = cached

        response = await client.aio.models.generate_content(
            model="gemini-2.5-pro",
            contents=prompt,
            config=config,
        )
        return response.text.strip() if response.text else "Keine AI-Insights verfügbar"
    except Exception as e:
        logger.error(f"Gemini API-Fehler: {e}")
        return f"⚠️ AI-Research fehlgeschlagen: {e}"


# ─────────────────────────────────────────────────────────────
# Hilfsfunktionen
# ─────────────────────────────────────────────────────────────

def _get_daily_movers(
    stocks: list[StockFullData],
    top_n: int = 2,
) -> list[tuple[StockFullData, float]]:
    """Gibt die Top-N Tagesgewinner und Top-N Tagesverlierer zurück.

    Returns:
        (winners, losers) – jeweils Liste von (StockFullData, daily_change_pct)
    """
    with_change = [
        (s, s.position.daily_change_pct)
        for s in stocks
        if s.position.ticker != "CASH" and s.position.daily_change_pct is not None and s.position.daily_change_pct != 0
    ]

    # Sortieren: höchste zuerst für Gewinner, niedrigste zuerst für Verlierer
    sorted_by_change = sorted(with_change, key=lambda x: x[1], reverse=True)

    winners = [(s, pct) for s, pct in sorted_by_change[:top_n] if pct > 0]
    losers = [(s, pct) for s, pct in sorted_by_change[-top_n:] if pct < 0]
    # Verlierer absteigend nach Verlust (größter Verlust zuerst)
    losers.sort(key=lambda x: x[1])

    return winners, losers

def _get_latest_report() -> Optional[AnalysisReport]:
    """Holt den letzten Analyse-Report aus dem State oder der Historie."""
    from state import portfolio_data

    report = portfolio_data.get("last_analysis")
    if report:
        return report

    # Fallback: aus Historie laden und als AnalysisReport rekonstruieren
    try:
        from engine.analysis import get_analysis_history
        history = get_analysis_history(days=1)
        if history:
            return None  # History ist dict-basiert, kein AnalysisReport
    except Exception:
        pass

    return None


def _sort_stocks_by_score(stocks: list[StockFullData]) -> list[StockFullData]:
    """Sortiert Aktien nach Score (absteigend)."""
    return sorted(
        [s for s in stocks if s.position.ticker != "CASH"],
        key=lambda s: s.score.total_score if s.score else 0,
        reverse=True,
    )


def _rating_icon(rating: Rating) -> str:
    """Gibt ein Emoji für das Rating zurück."""
    return {
        Rating.BUY: "🟢",
        Rating.HOLD: "🟡",
        Rating.SELL: "🔴",
    }.get(rating, "⚪")


def _fear_greed_emoji(value: int) -> str:
    """Gibt ein Emoji für den Fear & Greed Index zurück."""
    if value <= 20:
        return "😱"  # Extreme Fear
    elif value <= 40:
        return "😟"  # Fear
    elif value <= 60:
        return "😐"  # Neutral
    elif value <= 80:
        return "😊"  # Greed
    else:
        return "🤑"  # Extreme Greed
