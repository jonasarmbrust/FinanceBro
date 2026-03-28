"""
CSV Portfolio Reader — Alternative data source to Parqet.

Reads portfolio positions from a CSV file or uploaded JSON data.
Expected CSV columns: ticker, shares, buy_price, buy_date (optional), currency (optional), sector (optional), name (optional)
"""

import csv
import os
from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger("finanzbro.csv_reader")


def parse_csv_file(file_path: str) -> list[dict]:
    """Parse a CSV file into a list of position dicts."""
    if not os.path.exists(file_path):
        logger.error(f"CSV file not found: {file_path}")
        return []

    with open(file_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        return _normalize_rows(list(reader))


def parse_csv_json(positions: list[dict]) -> list[dict]:
    """Parse uploaded JSON positions (from frontend CSV upload)."""
    return _normalize_rows(positions)


def _normalize_rows(rows: list[dict]) -> list[dict]:
    """Normalize CSV rows into standard portfolio position format."""
    positions = []
    for row in rows:
        # Normalize keys to lowercase
        row = {k.lower().strip(): v for k, v in row.items()}

        ticker = row.get('ticker', '').strip().upper()
        if not ticker:
            continue

        # Skip cash rows
        if ticker in ('CASH', 'cash', ''):
            continue

        try:
            shares = float(row.get('shares', 0))
            buy_price = float(row.get('buy_price', 0))
        except (ValueError, TypeError):
            logger.warning(f"Skipping invalid row for ticker {ticker}: shares/buy_price not numeric")
            continue

        if shares <= 0:
            continue

        currency = row.get('currency', 'USD').strip().upper()
        if currency not in ('USD', 'EUR', 'GBP', 'CHF', 'CAD', 'JPY'):
            currency = 'USD'

        buy_date = _parse_date(row.get('buy_date', ''))
        sector = row.get('sector', '').strip() or None
        name = row.get('name', '').strip() or ticker

        positions.append({
            'ticker': ticker,
            'name': name,
            'shares': shares,
            'buy_price': buy_price,
            'buy_date': buy_date,
            'currency': currency,
            'sector': sector,
            'source': 'csv',
        })

    logger.info(f"Parsed {len(positions)} positions from CSV")
    return positions


def _parse_date(date_str: str) -> Optional[str]:
    """Try to parse a date string into ISO format."""
    if not date_str or not date_str.strip():
        return None

    date_str = date_str.strip()
    for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%m/%d/%Y', '%d/%m/%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(date_str, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue

    return None


def csv_positions_to_portfolio_format(positions: list[dict], prices: dict = None) -> list[dict]:
    """
    Convert CSV positions to the internal portfolio format expected by the scoring engine.

    This produces the same structure as Parqet positions so the rest of
    the pipeline (scoring, rebalancing, analytics) works unchanged.
    """
    portfolio = []
    for pos in positions:
        ticker = pos['ticker']
        current_price = prices.get(ticker, pos['buy_price']) if prices else pos['buy_price']
        value = current_price * pos['shares']
        cost_basis = pos['buy_price'] * pos['shares']
        pnl = value - cost_basis
        pnl_pct = ((current_price / pos['buy_price']) - 1) * 100 if pos['buy_price'] > 0 else 0

        portfolio.append({
            'ticker': ticker,
            'name': pos.get('name', ticker),
            'shares': pos['shares'],
            'currentPrice': current_price,
            'buyPrice': pos['buy_price'],
            'totalValue': value,
            'pnl': pnl,
            'pnlPercent': pnl_pct,
            'currency': pos.get('currency', 'USD'),
            'sector': pos.get('sector'),
            'buy_date': pos.get('buy_date'),
            'source': 'csv',
        })

    return portfolio
