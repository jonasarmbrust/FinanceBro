"""Tests for fetchers/csv_reader.py — CSV Portfolio Import."""

import os
import tempfile
import pytest
from fetchers.csv_reader import (
    parse_csv_file,
    parse_csv_json,
    csv_positions_to_portfolio_format,
    _parse_date,
    _normalize_rows,
)


class TestParseCsvJson:
    """Test JSON-based CSV parsing (from frontend upload)."""

    def test_basic_positions(self):
        data = [
            {"ticker": "AAPL", "shares": "10", "buy_price": "150.00"},
            {"ticker": "MSFT", "shares": "5", "buy_price": "280.00"},
        ]
        result = parse_csv_json(data)
        assert len(result) == 2
        assert result[0]["ticker"] == "AAPL"
        assert result[0]["shares"] == 10.0
        assert result[0]["buy_price"] == 150.0
        assert result[0]["source"] == "csv"

    def test_ticker_normalized_to_upper(self):
        data = [{"ticker": "aapl", "shares": "10", "buy_price": "150"}]
        result = parse_csv_json(data)
        assert result[0]["ticker"] == "AAPL"

    def test_skips_empty_ticker(self):
        data = [
            {"ticker": "", "shares": "10", "buy_price": "100"},
            {"ticker": "AAPL", "shares": "10", "buy_price": "150"},
        ]
        result = parse_csv_json(data)
        assert len(result) == 1

    def test_skips_cash_rows(self):
        data = [
            {"ticker": "CASH", "shares": "1", "buy_price": "5000"},
            {"ticker": "AAPL", "shares": "10", "buy_price": "150"},
        ]
        result = parse_csv_json(data)
        assert len(result) == 1
        assert result[0]["ticker"] == "AAPL"

    def test_skips_zero_shares(self):
        data = [{"ticker": "AAPL", "shares": "0", "buy_price": "150"}]
        result = parse_csv_json(data)
        assert len(result) == 0

    def test_skips_invalid_numeric(self):
        data = [{"ticker": "AAPL", "shares": "abc", "buy_price": "150"}]
        result = parse_csv_json(data)
        assert len(result) == 0

    def test_default_currency(self):
        data = [{"ticker": "AAPL", "shares": "10", "buy_price": "150"}]
        result = parse_csv_json(data)
        assert result[0]["currency"] == "USD"

    def test_valid_currencies(self):
        for curr in ["USD", "EUR", "GBP", "CHF"]:
            data = [{"ticker": "AAPL", "shares": "10", "buy_price": "150", "currency": curr}]
            result = parse_csv_json(data)
            assert result[0]["currency"] == curr

    def test_invalid_currency_defaults_to_usd(self):
        data = [{"ticker": "AAPL", "shares": "10", "buy_price": "150", "currency": "XYZ"}]
        result = parse_csv_json(data)
        assert result[0]["currency"] == "USD"

    def test_optional_fields(self):
        data = [{
            "ticker": "AAPL",
            "shares": "10",
            "buy_price": "150",
            "buy_date": "2024-03-15",
            "sector": "Technology",
            "name": "Apple Inc.",
        }]
        result = parse_csv_json(data)
        assert result[0]["buy_date"] == "2024-03-15"
        assert result[0]["sector"] == "Technology"
        assert result[0]["name"] == "Apple Inc."

    def test_name_defaults_to_ticker(self):
        data = [{"ticker": "AAPL", "shares": "10", "buy_price": "150"}]
        result = parse_csv_json(data)
        assert result[0]["name"] == "AAPL"

    def test_empty_list(self):
        result = parse_csv_json([])
        assert result == []


class TestParseCsvFile:
    """Test file-based CSV parsing."""

    def test_valid_csv_file(self):
        content = "ticker,shares,buy_price\nAAPL,10,150\nMSFT,5,280\n"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write(content)
            f.flush()
            result = parse_csv_file(f.name)
        os.unlink(f.name)
        assert len(result) == 2

    def test_nonexistent_file(self):
        result = parse_csv_file("/nonexistent/path.csv")
        assert result == []

    def test_csv_with_bom(self):
        content = "ticker,shares,buy_price\nAAPL,10,150\n"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8-sig') as f:
            f.write(content)
            f.flush()
            result = parse_csv_file(f.name)
        os.unlink(f.name)
        assert len(result) == 1


class TestParseDate:
    """Test date parsing helper."""

    def test_iso_format(self):
        assert _parse_date("2024-03-15") == "2024-03-15"

    def test_german_format(self):
        assert _parse_date("15.03.2024") == "2024-03-15"

    def test_us_format(self):
        assert _parse_date("03/15/2024") == "2024-03-15"

    def test_empty_string(self):
        assert _parse_date("") is None

    def test_none(self):
        assert _parse_date(None) is None

    def test_invalid_date(self):
        assert _parse_date("not-a-date") is None


class TestCsvToPortfolioFormat:
    """Test conversion to internal portfolio format."""

    def test_basic_conversion(self):
        positions = [{
            "ticker": "AAPL",
            "name": "Apple Inc.",
            "shares": 10,
            "buy_price": 150.0,
            "currency": "USD",
            "sector": "Technology",
            "buy_date": "2024-01-01",
        }]
        result = csv_positions_to_portfolio_format(positions)
        assert len(result) == 1
        assert result[0]["ticker"] == "AAPL"
        assert result[0]["shares"] == 10
        assert result[0]["currentPrice"] == 150.0  # No live prices, falls back to buy_price
        assert result[0]["totalValue"] == 1500.0
        assert result[0]["source"] == "csv"

    def test_with_live_prices(self):
        positions = [{"ticker": "AAPL", "name": "Apple", "shares": 10, "buy_price": 150.0, "currency": "USD"}]
        prices = {"AAPL": 200.0}
        result = csv_positions_to_portfolio_format(positions, prices)
        assert result[0]["currentPrice"] == 200.0
        assert result[0]["totalValue"] == 2000.0
        assert result[0]["pnl"] == 500.0

    def test_pnl_calculation(self):
        positions = [{"ticker": "AAPL", "name": "Apple", "shares": 10, "buy_price": 100.0, "currency": "USD"}]
        prices = {"AAPL": 120.0}
        result = csv_positions_to_portfolio_format(positions, prices)
        assert result[0]["pnl"] == 200.0  # (120-100) * 10
        assert abs(result[0]["pnlPercent"] - 20.0) < 0.01
