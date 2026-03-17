"""FinanzBro - Wöchentlicher Performance-Digest (Gemini 2.0 Flash).

Freitags-Report nach Börsenschluss mit Wochenrückblick:
  - Wochen-Performance (P&L)
  - Score-Veränderungen (Trends)
  - Trendwende-Aktien
  - KI-generierte Zusammenfassung

Wird via Cloud Run Job (Freitag 22:30 CET, nach US-Börsenschluss) oder manuell getriggert.
"""
import logging
from datetime import datetime, timedelta

from config import settings

logger = logging.getLogger(__name__)


async def send_weekly_digest():
    """Erstellt und sendet den wöchentlichen Portfolio-Digest via Telegram."""
    if not settings.telegram_configured:
        logger.info("Weekly Digest übersprungen (Telegram nicht konfiguriert)")
        return

    from state import portfolio_data
    summary = portfolio_data.get("summary")
    if not summary or not summary.stocks:
        logger.info("Weekly Digest übersprungen (keine Portfolio-Daten)")
        return

    try:
        # 1. Score-Historie laden
        from engine.analysis import get_analysis_history
        history = get_analysis_history(days=7)

        # 2. Wochen-Daten berechnen
        digest_data = _build_digest_data(summary, history)

        # 3. KI-Zusammenfassung generieren
        ai_summary = ""
        if settings.gemini_configured:
            ai_summary = await _generate_ai_summary(digest_data)

        # 4. Report formatieren
        report = _format_digest(digest_data, ai_summary)

        # 5. Via Telegram senden
        from services.telegram import send_message
        await send_message(report, chat_id=settings.TELEGRAM_CHAT_ID)
        logger.info(f"📧 Wöchentlicher Digest gesendet ({len(report)} Zeichen)")

    except Exception as e:
        logger.error(f"Weekly Digest fehlgeschlagen: {e}")


def _build_digest_data(summary, history: list[dict]) -> dict:
    """Berechnet die Kennzahlen für den Wochen-Digest."""
    data = {
        "total_value": summary.total_value,
        "total_pnl": summary.total_pnl,
        "total_pnl_pct": summary.total_pnl_percent,
        "num_positions": summary.num_positions,
        "score_changes": [],
        "best_performer": None,
        "worst_performer": None,
    }

    # Score-Veränderungen aus Historie berechnen
    if len(history) >= 2:
        first = history[0].get("scores", {})
        last = history[-1].get("scores", {})

        changes = []
        for ticker, latest in last.items():
            if ticker in first:
                diff = latest["score"] - first[ticker]["score"]
                if abs(diff) >= 2:  # Nur relevante Änderungen
                    changes.append({
                        "ticker": ticker,
                        "change": round(diff, 1),
                        "new_score": latest["score"],
                        "new_rating": latest["rating"],
                    })

        data["score_changes"] = sorted(changes, key=lambda x: abs(x["change"]), reverse=True)[:5]

    # Beste/schlechteste Position (nach P&L %)
    stocks = [s for s in summary.stocks if s.position.ticker != "CASH"]
    if stocks:
        best = max(stocks, key=lambda s: s.position.pnl_percent)
        worst = min(stocks, key=lambda s: s.position.pnl_percent)
        data["best_performer"] = {
            "ticker": best.position.ticker,
            "pnl_pct": best.position.pnl_percent,
        }
        data["worst_performer"] = {
            "ticker": worst.position.ticker,
            "pnl_pct": worst.position.pnl_percent,
        }

    return data


async def _generate_ai_summary(digest_data: dict) -> str:
    """Generiert eine KI-Zusammenfassung via Gemini 2.0 Flash."""
    try:
        from services.vertex_ai import get_client

        client = get_client()

        changes_text = ""
        if digest_data["score_changes"]:
            lines = []
            for c in digest_data["score_changes"]:
                arrow = "↑" if c["change"] > 0 else "↓"
                lines.append(f"  {c['ticker']}: {arrow}{abs(c['change']):.0f} → {c['new_score']:.0f} ({c['new_rating']})")
            changes_text = "\n".join(lines)

        prompt = (
            "Du bist ein Finanzanalyst. Erstelle eine kurze Wochenzusammenfassung "
            "(3-4 Sätze, max 400 Zeichen) auf Deutsch für folgendes Portfolio:\n\n"
            f"Portfoliowert: {digest_data['total_value']:,.0f} EUR\n"
            f"Gesamt-P&L: {digest_data['total_pnl']:+,.0f} EUR ({digest_data['total_pnl_pct']:+.1f}%)\n"
        )
        if digest_data["best_performer"]:
            prompt += f"Bester: {digest_data['best_performer']['ticker']} ({digest_data['best_performer']['pnl_pct']:+.1f}%)\n"
        if digest_data["worst_performer"]:
            prompt += f"Schwächster: {digest_data['worst_performer']['ticker']} ({digest_data['worst_performer']['pnl_pct']:+.1f}%)\n"
        if changes_text:
            prompt += f"\nScore-Veränderungen:\n{changes_text}\n"

        prompt += "\nFokus auf Trends, Auffälligkeiten und Ausblick. Keine Grüße oder Einleitung."

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )

        return response.text.strip() if response.text else ""

    except Exception as e:
        logger.warning(f"AI-Summary für Digest fehlgeschlagen: {e}")
        return ""


def _format_digest(data: dict, ai_summary: str) -> str:
    """Formatiert den Wochen-Digest als Telegram-Nachricht."""
    lines = [
        "📊 *FinanzBro Wochen-Digest*",
        f"_{datetime.now().strftime('%d.%m.%Y')}_\n",
        f"💰 Portfoliowert: {data['total_value']:,.2f} EUR",
        f"📈 Gesamt-P&L: {data['total_pnl']:+,.2f} EUR ({data['total_pnl_pct']:+.1f}%)",
        f"📋 Positionen: {data['num_positions']}",
    ]

    if data["best_performer"]:
        lines.append(f"\n🏆 Bester: {data['best_performer']['ticker']} ({data['best_performer']['pnl_pct']:+.1f}%)")
    if data["worst_performer"]:
        lines.append(f"📉 Schwächster: {data['worst_performer']['ticker']} ({data['worst_performer']['pnl_pct']:+.1f}%)")

    if data["score_changes"]:
        lines.append("\n📊 *Score-Veränderungen der Woche:*")
        for c in data["score_changes"][:5]:
            arrow = "↑" if c["change"] > 0 else "↓"
            emoji = "🟢" if c["change"] > 0 else "🔴"
            lines.append(f"  {emoji} {c['ticker']}: {arrow}{abs(c['change']):.0f} → {c['new_score']:.0f}")

    if ai_summary:
        lines.append(f"\n🤖 *KI-Einschätzung:*\n{ai_summary}")

    return "\n".join(lines)
