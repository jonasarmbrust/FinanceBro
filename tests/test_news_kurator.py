"""Tests für den News-Kurator Service."""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest


class TestCheckPortfolioNews:
    """Tests für die Hauptfunktion check_portfolio_news."""

    @pytest.mark.asyncio
    async def test_no_gemini_returns_false(self):
        """Ohne Gemini-Config wird False zurückgegeben."""
        with patch("services.news_kurator.settings") as mock:
            mock.gemini_configured = False
            mock.telegram_configured = True

            from services.news_kurator import check_portfolio_news
            result = await check_portfolio_news()
            assert result is False

    @pytest.mark.asyncio
    async def test_no_telegram_returns_false(self):
        """Ohne Telegram-Config wird False zurückgegeben."""
        with patch("services.news_kurator.settings") as mock:
            mock.gemini_configured = True
            mock.telegram_configured = False

            from services.news_kurator import check_portfolio_news
            result = await check_portfolio_news()
            assert result is False

    @pytest.mark.asyncio
    async def test_no_portfolio_data_returns_false(self):
        """Ohne Portfolio-Daten wird False zurückgegeben."""
        with patch("services.news_kurator.settings") as mock, \
             patch("state.portfolio_data", {"summary": None}):
            mock.gemini_configured = True
            mock.telegram_configured = True

            from services.news_kurator import check_portfolio_news
            result = await check_portfolio_news()
            assert result is False


class TestDeduplication:
    """Tests für die Deduplizierungs-Logik."""

    def test_sent_headlines_set(self):
        """_sent_headlines ist ein Set für Deduplizierung."""
        from services.news_kurator import _sent_headlines
        assert isinstance(_sent_headlines, set)


class TestFormatAlerts:
    """Tests für die Alert-Formatierung."""

    def test_format_single_alert(self):
        """Einzelner Alert wird korrekt formatiert."""
        from services.news_kurator import _format_alerts

        alerts = [{
            "ticker": "AAPL",
            "headline": "Apple meldet Rekordumsatz im Q1",
            "impact": "positiv",
            "urgency": "hoch",
            "category": "earnings",
        }]

        result = _format_alerts(alerts, "Märkte optimistisch")

        assert "AAPL" in result
        assert "Rekordumsatz" in result
        assert "🟢" in result  # positiv
        assert "🔥" in result  # hoch
        assert "📊" in result  # earnings
        assert "Märkte optimistisch" in result
        assert "1 Alert(s)" in result

    def test_format_multiple_alerts(self):
        """Mehrere Alerts werden korrekt formatiert."""
        from services.news_kurator import _format_alerts

        alerts = [
            {
                "ticker": "NVDA",
                "headline": "NVDA übertrifft Erwartungen",
                "impact": "positiv",
                "urgency": "hoch",
                "category": "earnings",
            },
            {
                "ticker": "TSLA",
                "headline": "Tesla CEO tritt zurück",
                "impact": "negativ",
                "urgency": "hoch",
                "category": "management",
            },
        ]

        result = _format_alerts(alerts, "")

        assert "NVDA" in result
        assert "TSLA" in result
        assert "🟢" in result  # positiv
        assert "🔴" in result  # negativ
        assert "2 Alert(s)" in result

    def test_format_empty_alerts(self):
        """Leere Alert-Liste erzeugt trotzdem Header."""
        from services.news_kurator import _format_alerts

        result = _format_alerts([], "Ruhiger Markt")
        assert "News-Alert" in result
        assert "0 Alert(s)" in result

    def test_format_all_impact_types(self):
        """Alle Impact-Typen verwenden korrekte Icons."""
        from services.news_kurator import _format_alerts

        for impact, icon in [("positiv", "🟢"), ("negativ", "🔴"), ("neutral", "🟡")]:
            alerts = [{
                "ticker": "TEST",
                "headline": "Test",
                "impact": impact,
                "urgency": "mittel",
                "category": "sonstiges",
            }]
            result = _format_alerts(alerts, "")
            assert icon in result


class TestNewsAlertSchema:
    """Tests für das Structured Output Schema."""

    def test_schema_has_required_fields(self):
        """Schema hat die erwarteten Required-Felder."""
        from services.news_kurator import NEWS_ALERT_SCHEMA

        assert "alerts" in NEWS_ALERT_SCHEMA["properties"]
        assert "market_mood" in NEWS_ALERT_SCHEMA["properties"]
        assert NEWS_ALERT_SCHEMA["required"] == ["alerts", "market_mood"]

    def test_alert_item_schema(self):
        """Alert-Items haben alle nötigen Felder."""
        from services.news_kurator import NEWS_ALERT_SCHEMA

        item_props = NEWS_ALERT_SCHEMA["properties"]["alerts"]["items"]["properties"]
        assert "ticker" in item_props
        assert "headline" in item_props
        assert "impact" in item_props
        assert "urgency" in item_props
        assert "category" in item_props

    def test_impact_enum_values(self):
        """Impact-Enum hat die erwarteten Werte."""
        from services.news_kurator import NEWS_ALERT_SCHEMA

        impact = NEWS_ALERT_SCHEMA["properties"]["alerts"]["items"]["properties"]["impact"]
        assert set(impact["enum"]) == {"positiv", "negativ", "neutral"}
