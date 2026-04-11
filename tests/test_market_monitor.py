"""Tests für services/market_monitor.py — Ad-hoc Market Event Alerting."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import date

from services.market_monitor import (
    check_market_events,
    get_monitor_status,
    _detect_portfolio_events,
    _detect_single_stock_events,
    _detect_fear_greed_events,
    _format_market_alert,
    _get_severity,
    _reset_daily,
    _sent_events,
    PORTFOLIO_CRASH_THRESHOLD,
    PORTFOLIO_RALLY_THRESHOLD,
    STOCK_CRASH_THRESHOLD,
    STOCK_SPIKE_THRESHOLD,
    FEAR_GREED_EXTREME_LOW,
    FEAR_GREED_SHIFT_THRESHOLD,
)


# ─────────────────────────────────────────────────────────────
# Helper: Mock-Objekte
# ─────────────────────────────────────────────────────────────

class MockPosition:
    def __init__(self, ticker="AAPL", name="Apple Inc.", daily_change_pct=0.0,
                 current_price=150.0, pnl_percent=5.0, sector="Technology"):
        self.ticker = ticker
        self.name = name
        self.daily_change_pct = daily_change_pct
        self.current_price = current_price
        self.pnl_percent = pnl_percent
        self.sector = sector
        self.price_currency = "EUR"


class MockScore:
    def __init__(self, total_score=65, rating_value="hold"):
        self.total_score = total_score
        self.rating = MagicMock(value=rating_value)


class MockStock:
    def __init__(self, ticker="AAPL", daily_change_pct=0.0, **kwargs):
        self.position = MockPosition(ticker=ticker, daily_change_pct=daily_change_pct, **kwargs)
        self.score = MockScore()


class MockFearGreed:
    def __init__(self, value=50, label="Neutral"):
        self.value = value
        self.label = label


class MockSummary:
    def __init__(self, stocks=None, daily_total_change_pct=0.0, daily_total_change=0.0,
                 total_value=50000.0, fear_greed=None):
        self.stocks = stocks or []
        self.daily_total_change_pct = daily_total_change_pct
        self.daily_total_change = daily_total_change
        self.total_value = total_value
        self.fear_greed = fear_greed
        self.num_positions = len(self.stocks)
        self.total_pnl = 2500.0
        self.total_pnl_percent = 5.0


# ─────────────────────────────────────────────────────────────
# Tests: Event Detection
# ─────────────────────────────────────────────────────────────

class TestPortfolioEvents:
    """Tests für Portfolio-Level Event Detection."""

    def test_no_event_normal_day(self):
        summary = MockSummary(daily_total_change_pct=-0.5, daily_total_change=-250)
        events = _detect_portfolio_events(summary)
        assert len(events) == 0

    def test_portfolio_crash_detected(self):
        summary = MockSummary(daily_total_change_pct=-3.5, daily_total_change=-1750)
        events = _detect_portfolio_events(summary)
        assert len(events) == 1
        assert events[0]["type"] == "portfolio_crash"
        assert events[0]["value"] == -3.5

    def test_portfolio_rally_detected(self):
        summary = MockSummary(daily_total_change_pct=4.2, daily_total_change=2100)
        events = _detect_portfolio_events(summary)
        assert len(events) == 1
        assert events[0]["type"] == "portfolio_rally"
        assert events[0]["value"] == 4.2

    def test_no_event_zero_change(self):
        summary = MockSummary(daily_total_change_pct=0.0, daily_total_change=0.0)
        events = _detect_portfolio_events(summary)
        assert len(events) == 0

    def test_no_event_none_change(self):
        summary = MockSummary(daily_total_change_pct=None, daily_total_change=0.0)
        events = _detect_portfolio_events(summary)
        assert len(events) == 0

    def test_crash_at_threshold(self):
        """Genau am Schwellenwert → Alert."""
        summary = MockSummary(
            daily_total_change_pct=PORTFOLIO_CRASH_THRESHOLD,
            daily_total_change=-1000,
        )
        events = _detect_portfolio_events(summary)
        assert len(events) == 1

    def test_just_above_crash_threshold(self):
        """Knapp über Crash-Schwelle → kein Alert."""
        summary = MockSummary(
            daily_total_change_pct=PORTFOLIO_CRASH_THRESHOLD + 0.1,
            daily_total_change=-950,
        )
        events = _detect_portfolio_events(summary)
        assert len(events) == 0


class TestSingleStockEvents:
    """Tests für Einzelaktien-Event Detection."""

    def test_stock_crash_detected(self):
        stocks = [MockStock(ticker="TSLA", daily_change_pct=-7.5, name="Tesla Inc.")]
        events = _detect_single_stock_events(stocks)
        assert len(events) == 1
        assert events[0]["type"] == "stock_crash"
        assert events[0]["ticker"] == "TSLA"

    def test_stock_spike_detected(self):
        stocks = [MockStock(ticker="NVDA", daily_change_pct=12.0, name="NVIDIA Corp.")]
        events = _detect_single_stock_events(stocks)
        assert len(events) == 1
        assert events[0]["type"] == "stock_spike"
        assert events[0]["ticker"] == "NVDA"

    def test_cash_ignored(self):
        stocks = [MockStock(ticker="CASH", daily_change_pct=-10.0)]
        events = _detect_single_stock_events(stocks)
        assert len(events) == 0

    def test_normal_move_no_event(self):
        stocks = [MockStock(ticker="AAPL", daily_change_pct=-2.0)]
        events = _detect_single_stock_events(stocks)
        assert len(events) == 0

    def test_multiple_events_sorted(self):
        stocks = [
            MockStock(ticker="TSLA", daily_change_pct=-8.0, name="Tesla"),
            MockStock(ticker="NVDA", daily_change_pct=10.0, name="NVIDIA"),
            MockStock(ticker="GME", daily_change_pct=-12.0, name="GameStop"),
        ]
        events = _detect_single_stock_events(stocks)
        assert len(events) == 3
        # Sortiert nach abs(value), größter zuerst
        assert events[0]["ticker"] == "GME"
        assert events[1]["ticker"] == "NVDA"

    def test_max_5_events(self):
        stocks = [
            MockStock(ticker=f"T{i}", daily_change_pct=-(6 + i), name=f"Test {i}")
            for i in range(10)
        ]
        events = _detect_single_stock_events(stocks)
        assert len(events) <= 5


class TestFearGreedEvents:
    """Tests für Fear & Greed Event Detection."""

    def test_extreme_fear_detected(self):
        summary = MockSummary(fear_greed=MockFearGreed(value=15, label="Extreme Fear"))
        events = _detect_fear_greed_events(summary)
        assert any(e["type"] == "extreme_fear" for e in events)

    def test_no_event_normal_fg(self):
        summary = MockSummary(fear_greed=MockFearGreed(value=50, label="Neutral"))
        events = _detect_fear_greed_events(summary)
        assert len(events) == 0

    def test_no_event_without_fg(self):
        summary = MockSummary(fear_greed=None)
        events = _detect_fear_greed_events(summary)
        assert len(events) == 0

    def test_shift_detected(self):
        import services.market_monitor as mm
        old_fg = mm._last_fear_greed
        mm._last_fear_greed = 60

        summary = MockSummary(fear_greed=MockFearGreed(value=40, label="Fear"))
        events = _detect_fear_greed_events(summary)
        assert any(e["type"] == "fear_greed_shift" for e in events)

        # Reset
        mm._last_fear_greed = old_fg

    def test_no_shift_small_change(self):
        import services.market_monitor as mm
        old_fg = mm._last_fear_greed
        mm._last_fear_greed = 50

        summary = MockSummary(fear_greed=MockFearGreed(value=45, label="Fear"))
        events = _detect_fear_greed_events(summary)
        shift_events = [e for e in events if e["type"] == "fear_greed_shift"]
        assert len(shift_events) == 0

        mm._last_fear_greed = old_fg


# ─────────────────────────────────────────────────────────────
# Tests: Formatierung
# ─────────────────────────────────────────────────────────────

class TestFormatting:
    """Tests für Telegram-Nachrichtenformatierung."""

    def test_format_crash_alert(self):
        events = [{
            "type": "portfolio_crash",
            "emoji": "🔴📉",
            "title": "Portfolio-Crash",
            "description": "Dein Portfolio verliert heute -3.5%",
        }]
        summary = MockSummary(
            daily_total_change=-1750,
            daily_total_change_pct=-3.5,
            total_value=48250,
        )
        msg = _format_market_alert(events, "", summary)
        assert "Market Alert" in msg
        assert "Portfolio-Crash" in msg
        assert "-3.5%" in msg

    def test_format_with_ai_context(self):
        events = [{
            "type": "stock_crash",
            "emoji": "🔴💥",
            "title": "TSLA Crash",
            "description": "Tesla stürzt ab: -8.0%",
        }]
        summary = MockSummary(daily_total_change=-500, daily_total_change_pct=-1.0)
        msg = _format_market_alert(events, "Fed hat Zinsen erhöht.", summary)
        assert "AI Einschätzung" in msg
        assert "Fed hat Zinsen" in msg

    def test_severity_portfolio_crash(self):
        events = [{"type": "portfolio_crash"}]
        assert "🔴🔴🔴" in _get_severity(events)

    def test_severity_stock_crash(self):
        events = [{"type": "stock_crash"}]
        assert "🔴🔴" in _get_severity(events)

    def test_severity_rally(self):
        events = [{"type": "portfolio_rally"}]
        assert "🟢" in _get_severity(events)


# ─────────────────────────────────────────────────────────────
# Tests: Status & Dedup
# ─────────────────────────────────────────────────────────────

class TestStatusAndDedup:
    """Tests für Status und Deduplizierung."""

    def test_get_status(self):
        status = get_monitor_status()
        assert "alerts_sent_today" in status
        assert "thresholds" in status
        assert "portfolio_crash" in status["thresholds"]
        assert "stock_crash" in status["thresholds"]

    def test_thresholds_correct(self):
        status = get_monitor_status()
        t = status["thresholds"]
        assert t["portfolio_crash"] == PORTFOLIO_CRASH_THRESHOLD
        assert t["portfolio_rally"] == PORTFOLIO_RALLY_THRESHOLD
        assert t["stock_crash"] == STOCK_CRASH_THRESHOLD
        assert t["stock_spike"] == STOCK_SPIKE_THRESHOLD

    def test_daily_reset(self):
        """State wird bei Tageswechsel zurückgesetzt."""
        import services.market_monitor as mm
        mm._state_date = date(2020, 1, 1)
        mm._alert_count = 99
        mm._sent_events = {"old_event"}

        _reset_daily()

        assert mm._alert_count == 0
        assert len(mm._sent_events) == 0


# ─────────────────────────────────────────────────────────────
# Tests: Integration (check_market_events)
# ─────────────────────────────────────────────────────────────

class TestCheckMarketEvents:
    """Integration-Tests für check_market_events."""

    @pytest.mark.asyncio
    async def test_no_data_returns_empty(self):
        import services.market_monitor as mm
        with patch.object(mm, "settings") as mock_settings:
            mock_settings.telegram_configured = True
            mock_settings.gemini_configured = False

            from state import portfolio_data
            old = portfolio_data.get("summary")
            portfolio_data["summary"] = None

            result = await mm.check_market_events()
            assert result["events_detected"] == 0

            portfolio_data["summary"] = old

    @pytest.mark.asyncio
    async def test_telegram_not_configured_skips(self):
        import services.market_monitor as mm
        with patch.object(mm, "settings") as mock_settings:
            mock_settings.telegram_configured = False
            result = await mm.check_market_events()
            assert result["events_detected"] == 0

    @pytest.mark.asyncio
    async def test_crash_triggers_alert(self):
        """Ein Portfolio-Crash soll Events erkennen."""
        import services.market_monitor as mm
        # Reset state
        mm._sent_events = set()
        mm._alert_count = 0
        mm._state_date = date.today()

        crash_stocks = [MockStock(ticker="AAPL", daily_change_pct=-1.5)]
        crash_summary = MockSummary(
            stocks=crash_stocks,
            daily_total_change_pct=-4.0,
            daily_total_change=-2000,
            fear_greed=MockFearGreed(value=50, label="Neutral"),
        )

        from state import portfolio_data
        old = portfolio_data.get("summary")
        portfolio_data["summary"] = crash_summary

        with patch.object(mm, "settings") as mock_settings, \
             patch("services.telegram.send_message", new_callable=AsyncMock, return_value=True):
            mock_settings.telegram_configured = True
            mock_settings.gemini_configured = False

            result = await mm.check_market_events(force=True)
            assert result["events_detected"] >= 1

        portfolio_data["summary"] = old
