import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
import json
from services.portfolio_history import (
    _load_local,
    _save_local,
    get_ytd,
    get_history_range,
    load_history,
    save_history,
    update_today,
    backfill_from_parqet
)

def test_load_save_local(tmp_path):
    with patch("services.portfolio_history.HISTORY_FILE", tmp_path / "portfolio_history.json"):
        data = _load_local()
        assert data == {"metadata": {}, "daily": []}

        test_data = {
            "metadata": {"test": "yes"},
            "daily": [{"date": "2026-01-01", "total_value": 100.0}]
        }
        _save_local(test_data)
        data = _load_local()
        assert data == test_data

def test_get_ytd(tmp_path):
    current_year = datetime.now().year
    with patch("services.portfolio_history.HISTORY_FILE", tmp_path / "portfolio_history.json"):
        # Empty
        assert get_ytd() is None

        # Correct calculation
        test_data = {
            "metadata": {},
            "daily": [
                {"date": f"{current_year}-01-01", "total_value": 100.0},
                {"date": f"{current_year}-01-15", "total_value": 110.0},
                {"date": f"{current_year}-02-01", "total_value": 115.0},
            ]
        }
        _save_local(test_data)
        assert get_ytd() == 15.0

def test_get_history_range(tmp_path):
    current_year = datetime.now().year
    with patch("services.portfolio_history.HISTORY_FILE", tmp_path / "portfolio_history.json"):
        test_data = {
            "metadata": {},
            "daily": [
                {"date": f"{current_year-1}-12-31", "total_value": 90.0},
                {"date": f"{current_year}-01-01", "total_value": 100.0},
                {"date": f"{current_year}-01-15", "total_value": 110.0},
            ]
        }
        _save_local(test_data)
        
        # Max
        data_max = get_history_range("max")
        assert len(data_max) == 3

        # YTD
        data_ytd = get_history_range("ytd")
        assert len(data_ytd) == 2
        assert data_ytd[0]["date"] == f"{current_year}-01-01"
