"""Tests für Rate Limiter und Refresh Pipeline."""
import time
import pytest
from unittest.mock import patch


class TestRateLimiter:
    """Tests für middleware/rate_limiter.py."""

    def setup_method(self):
        """Reset rate limiter state before each test."""
        from middleware.rate_limiter import _rate_buckets
        _rate_buckets.clear()

    def test_check_rate_limit_allows_within_limit(self):
        from middleware.rate_limiter import check_rate_limit
        # Should not raise for first call
        assert check_rate_limit("advisor_evaluate") is True

    def test_check_rate_limit_blocks_over_limit(self):
        from middleware.rate_limiter import check_rate_limit, RATE_LIMITS
        from fastapi import HTTPException

        limit = RATE_LIMITS["advisor_evaluate"]["max_calls"]
        # Use up all calls
        for _ in range(limit):
            check_rate_limit("advisor_evaluate")

        # Next call should raise 429
        with pytest.raises(HTTPException) as exc_info:
            check_rate_limit("advisor_evaluate")
        assert exc_info.value.status_code == 429

    def test_check_rate_limit_resets_after_window(self):
        from middleware.rate_limiter import check_rate_limit, _rate_buckets, RATE_LIMITS
        from fastapi import HTTPException

        limit = RATE_LIMITS["advisor_evaluate"]["max_calls"]
        # Use up all calls
        for _ in range(limit):
            check_rate_limit("advisor_evaluate")

        # Simulate window expiry
        _rate_buckets["advisor_evaluate"]["window_start"] = time.monotonic() - 999

        # Should work again
        assert check_rate_limit("advisor_evaluate") is True

    def test_check_rate_limit_different_endpoints_independent(self):
        from middleware.rate_limiter import check_rate_limit, RATE_LIMITS
        from fastapi import HTTPException

        # Max out advisor_evaluate
        limit = RATE_LIMITS["advisor_evaluate"]["max_calls"]
        for _ in range(limit):
            check_rate_limit("advisor_evaluate")

        # advisor_chat should still work
        assert check_rate_limit("advisor_chat") is True

    def test_check_rate_limit_uses_default_for_unknown(self):
        from middleware.rate_limiter import check_rate_limit, RATE_LIMITS
        # Unknown endpoint should use 'default' config (30 calls)
        for _ in range(30):
            check_rate_limit("unknown_endpoint")

    def test_shadow_run_limit(self):
        from middleware.rate_limiter import check_rate_limit, RATE_LIMITS
        from fastapi import HTTPException

        limit = RATE_LIMITS["shadow_run"]["max_calls"]
        for _ in range(limit):
            check_rate_limit("shadow_run")

        with pytest.raises(HTTPException):
            check_rate_limit("shadow_run")


class TestRefreshPipeline:
    """Tests für die refaktorierte Refresh-Pipeline."""

    def test_phase_functions_exist(self):
        """Verify the pipeline phase functions are importable."""
        from services.refresh import (
            _phase_fetch_sources,
            _phase_build_summary,
            _phase_post_analysis,
        )
        assert callable(_phase_fetch_sources)
        assert callable(_phase_build_summary)
        assert callable(_phase_post_analysis)


class TestStateAccessors:
    """Tests für state.py Typed Accessors."""

    def test_get_summary_returns_none_initially(self):
        from state import get_summary, portfolio_data
        portfolio_data["summary"] = None
        assert get_summary() is None

    def test_set_summary_updates_state(self):
        from state import get_summary, set_summary, portfolio_data
        set_summary("test_value")
        assert get_summary() == "test_value"
        portfolio_data["summary"] = None  # cleanup

    def test_is_refreshing_default_false(self):
        from state import is_refreshing, portfolio_data
        portfolio_data["refreshing"] = False
        assert is_refreshing() is False

    def test_set_refreshing(self):
        from state import is_refreshing, set_refreshing, portfolio_data
        set_refreshing(True)
        assert is_refreshing() is True
        set_refreshing(False)
        assert is_refreshing() is False


class TestHealthCheck:
    """Tests für den erweiterten Health Check."""

    def test_health_endpoint_exists(self):
        from main import app
        routes = [r.path for r in app.routes]
        assert "/health" in routes


class TestDatabaseIndexes:
    """Tests für die neuen DB-Indexes."""

    def test_indexes_are_created(self):
        from database import init_db, _get_conn
        init_db()
        conn = _get_conn()
        indexes = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
        index_names = {r[0] for r in indexes}
        assert "idx_snapshots_date" in index_names
        assert "idx_reports_timestamp" in index_names
        assert "idx_shadow_perf_date" in index_names
        assert "idx_shadow_log_timestamp" in index_names
