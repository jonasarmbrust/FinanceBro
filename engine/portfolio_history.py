"""FinanzBro - Portfolio History Engine

Rekonstruiert den historischen Wert jeder Einzelaktie und des
Gesamtportfolios über die Zeit.

Datenquellen:
  1. Parqet Activities → Täglicher Aktienbestand (Shares pro Ticker)
  2. yfinance → Historische Tagesschlusskurse

Persistenz:
  SQLite-Tabelle `price_history` speichert bereits abgerufene Kurse.
  Beim nächsten Aufruf werden nur neue Tage nachgeladen (inkrementell).
  → Spart API-Calls, übersteht Restarts, funktioniert auch bei Teil-Abrufen.
"""
import logging
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta

from config import settings

logger = logging.getLogger(__name__)

# SQLite-Pfad (gleiche DB wie database.py)
_DB_PATH = settings.CACHE_DIR / "finanzbro.db"


# ─────────────────────────────────────────────────────────────
# SQLite Price Cache
# ─────────────────────────────────────────────────────────────

def _init_price_table():
    """Erstellt die price_history Tabelle falls sie nicht existiert."""
    conn = sqlite3.connect(str(_DB_PATH), timeout=10)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            close REAL NOT NULL,
            PRIMARY KEY (ticker, date)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_price_ticker ON price_history(ticker)"
    )
    conn.commit()
    conn.close()


def _load_cached_prices(tickers: list[str]) -> dict[str, dict[str, float]]:
    """Lädt alle gespeicherten Kurse aus SQLite.

    Returns: {ticker: {date: close, ...}, ...}
    """
    conn = sqlite3.connect(str(_DB_PATH), timeout=10)
    result: dict[str, dict[str, float]] = defaultdict(dict)
    try:
        placeholders = ",".join("?" for _ in tickers)
        rows = conn.execute(
            f"SELECT ticker, date, close FROM price_history WHERE ticker IN ({placeholders})",
            tickers,
        ).fetchall()
        for ticker, date, close in rows:
            result[ticker][date] = close
    except Exception as e:
        logger.debug(f"Price-Cache laden fehlgeschlagen: {e}")
    finally:
        conn.close()
    return dict(result)


def _save_prices_to_cache(prices: dict[str, dict[str, float]]):
    """Speichert neue Kurse in SQLite (UPSERT)."""
    conn = sqlite3.connect(str(_DB_PATH), timeout=10)
    try:
        rows = []
        for ticker, date_prices in prices.items():
            for date, close in date_prices.items():
                rows.append((ticker, date, close))
        if rows:
            conn.executemany(
                """INSERT INTO price_history (ticker, date, close)
                   VALUES (?, ?, ?)
                   ON CONFLICT(ticker, date) DO UPDATE SET close=excluded.close""",
                rows,
            )
            conn.commit()
            logger.info(f"💾 Price-Cache: {len(rows)} Kurse gespeichert")
    except Exception as e:
        logger.warning(f"Price-Cache speichern fehlgeschlagen: {e}")
    finally:
        conn.close()


def _get_last_cached_date(ticker: str) -> str | None:
    """Gibt das letzte gecachte Datum für einen Ticker zurück."""
    conn = sqlite3.connect(str(_DB_PATH), timeout=10)
    try:
        row = conn.execute(
            "SELECT MAX(date) FROM price_history WHERE ticker = ?", (ticker,)
        ).fetchone()
        return row[0] if row and row[0] else None
    except Exception:
        return None
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────
# Position Reconstruction
# ─────────────────────────────────────────────────────────────

def reconstruct_daily_holdings(activities: list[dict]) -> dict[str, list[tuple[str, float]]]:
    """Rekonstruiert aus Activities den Aktienbestand pro Tag.

    Für jeden Ticker wird eine Timeline erstellt:
    [(date, cumulative_shares), ...]

    Nur buy/sell/transfer_in/transfer_out werden berücksichtigt.
    """
    events: dict[str, list[tuple[str, float]]] = defaultdict(list)

    for act in activities:
        act_type = (act.get("type") or "").lower()
        ticker = act.get("ticker", "")
        date = act.get("date", "")
        shares = float(act.get("shares") or 0)

        if not ticker or not date or shares <= 0:
            continue
        if ticker == "CASH":
            continue

        if act_type in ("buy", "kauf", "purchase", "transferin", "transfer_in"):
            events[ticker].append((date, shares))
        elif act_type in ("sell", "verkauf", "sale", "transferout", "transfer_out"):
            events[ticker].append((date, -shares))

    holdings: dict[str, list[tuple[str, float]]] = {}
    for ticker, ticker_events in events.items():
        ticker_events.sort(key=lambda x: x[0])
        cumulative = 0.0
        timeline = []
        for date, delta in ticker_events:
            cumulative += delta
            if abs(cumulative) < 0.001:
                cumulative = 0.0
            timeline.append((date, cumulative))
        if timeline:
            holdings[ticker] = timeline

    return holdings


def _get_shares_on_date(timeline: list[tuple[str, float]], date_str: str) -> float:
    """Gibt die Shares für einen Ticker an einem bestimmten Datum zurück."""
    result = 0.0
    for event_date, shares in timeline:
        if event_date <= date_str:
            result = shares
        else:
            break
    return result


# ─────────────────────────────────────────────────────────────
# Cash Balance Reconstruction
# ─────────────────────────────────────────────────────────────

def reconstruct_cash_timeline(raw_activities: list[dict]) -> list[tuple[str, float]]:
    """Rekonstruiert den Cash-Bestand aus rohen Parqet Activities.

    Cash-Logik:
      + transferin (Cash)   → Einzahlung
      - buy (Cash)          → Geld fließt in Aktie
      + sell (Cash)          → Geld fließt aus Aktie zurück
      + dividend (Cash)      → Dividende
      + interest (Cash)      → Zinsen
      - transferout (Cash)   → Auszahlung

    Returns: [(date, cumulative_cash), ...] sortiert nach Datum
    """
    events: list[tuple[str, float]] = []

    for act in raw_activities:
        hat = act.get("holdingAssetType", "")
        if hat != "Cash":
            continue

        act_type = (act.get("type") or "").lower()
        date = act.get("datetime") or act.get("date") or ""
        if date and "T" in date:
            date = date.split("T")[0]
        amount = float(act.get("amount") or 0)

        if not date:
            continue

        if act_type in ("transferin", "transfer_in"):
            events.append((date, amount))
        elif act_type in ("transferout", "transfer_out"):
            events.append((date, -amount))
        elif act_type in ("buy", "kauf", "purchase"):
            events.append((date, -amount))  # Cash geht raus
        elif act_type in ("sell", "verkauf", "sale"):
            events.append((date, amount))   # Cash kommt rein
        elif act_type in ("dividend",):
            events.append((date, amount))
        elif act_type in ("interest",):
            events.append((date, amount))

    events.sort(key=lambda x: x[0])

    # Kumulieren
    timeline = []
    cumulative = 0.0
    for date, delta in events:
        cumulative += delta
        if abs(cumulative) < 0.01:
            cumulative = 0.0
        timeline.append((date, cumulative))

    return timeline


# ─────────────────────────────────────────────────────────────
# Main Entry Point
# ─────────────────────────────────────────────────────────────

async def build_portfolio_history(
    activities: list[dict],
    period_days: int = 180,
    raw_activities: list[dict] | None = None,
) -> dict:
    """Baut die komplette Portfolio-Historie für das Diagramm.

    Nutzt SQLite-Cache für bereits abgerufene Kurse und lädt nur
    fehlende Tage inkrementell von yfinance nach.

    Args:
        activities: Geparste Activities (ohne Cash)
        period_days: Zeitraum in Tagen
        raw_activities: Rohe Parqet Activities (inkl. Cash) für Cash-Rekonstruktion

    Returns:
        {
            "dates": ["2024-01-02", ...],
            "stocks": {
                "AAPL": {"name": "Apple", "values": [1750.0, ...]},
                "💵 Cash": {"name": "Cash", "values": [500.0, ...]},
                ...
            },
            "total": [12500.0, ...],
            "total_cost": [11000.0, ...]
        }
    """
    if not activities:
        return {"dates": [], "stocks": {}, "total": [], "total_cost": []}

    # Tabelle sicherstellen
    _init_price_table()

    # 1. Holdings rekonstruieren
    holdings = reconstruct_daily_holdings(activities)
    if not holdings:
        return {"dates": [], "stocks": {}, "total": [], "total_cost": []}

    # 2. Cash-Timeline rekonstruieren (wenn raw data verfügbar)
    cash_timeline = None
    if raw_activities:
        cash_timeline = reconstruct_cash_timeline(raw_activities)

    # 3. Datumsgrenzen bestimmen
    all_dates = []
    for timeline in holdings.values():
        for date_str, _ in timeline:
            all_dates.append(date_str)
    if cash_timeline:
        for date_str, _ in cash_timeline:
            all_dates.append(date_str)

    if not all_dates:
        return {"dates": [], "stocks": {}, "total": [], "total_cost": []}

    earliest = min(all_dates)
    today = datetime.now().strftime("%Y-%m-%d")

    if period_days > 0 and period_days < 9999:
        cutoff = (datetime.now() - timedelta(days=period_days)).strftime("%Y-%m-%d")
        start_date = max(earliest, cutoff)
    else:
        start_date = earliest

    # 4. Ticker-Namen aus Activities extrahieren
    ticker_names: dict[str, str] = {}
    for act in activities:
        t = act.get("ticker", "")
        n = act.get("name", "")
        if t and n and t not in ticker_names:
            ticker_names[t] = n

    # 5. Historische Kurse: Cache + inkrementeller yfinance-Abruf
    tickers = list(holdings.keys())
    prices = await _fetch_prices_with_cache(tickers, start_date, today)

    if not prices:
        logger.warning("Keine historischen Kurse verfügbar (Cache + yfinance)")
        return {"dates": [], "stocks": {}, "total": [], "total_cost": []}

    # 6. Gemeinsame Datums-Achse aus den Preisdaten ableiten
    all_price_dates: set[str] = set()
    for ticker_prices in prices.values():
        all_price_dates.update(ticker_prices.keys())

    if not all_price_dates:
        return {"dates": [], "stocks": {}, "total": [], "total_cost": []}

    dates = sorted(d for d in all_price_dates if d >= start_date)
    if not dates:
        return {"dates": [], "stocks": {}, "total": [], "total_cost": []}

    # 7. Einstandskosten-Timeline
    cost_timeline = _reconstruct_cost_timeline(activities, dates)

    # 8. Werte berechnen: Shares × Kurs pro Tag
    stocks_data: dict[str, dict] = {}
    total_values = [0.0] * len(dates)

    for ticker, timeline in holdings.items():
        if ticker not in prices or not prices[ticker]:
            continue

        values = []
        for i, date_str in enumerate(dates):
            shares = _get_shares_on_date(timeline, date_str)
            price = prices[ticker].get(date_str, 0.0)

            # Forward-fill: letzten bekannten Preis nutzen
            if price <= 0:
                for prev_date in reversed(dates[:i]):
                    price = prices[ticker].get(prev_date, 0.0)
                    if price > 0:
                        break

            value = round(shares * price, 2) if shares > 0 and price > 0 else 0.0
            values.append(value)
            total_values[i] += value

        if any(v > 0 for v in values):
            name = ticker_names.get(ticker, ticker)
            stocks_data[ticker] = {"name": name, "values": values}

    # 9. Cash-Bestand zu den Werten hinzufügen
    if cash_timeline and len(cash_timeline) > 0:
        cash_values = []
        for date_str in dates:
            cash = _get_shares_on_date(cash_timeline, date_str)
            cash = max(cash, 0)  # Kein negativer Cash
            cash_values.append(round(cash, 2))
            # Cash zum Gesamtwert addieren
            total_values[dates.index(date_str)] += cash

        if any(v > 0 for v in cash_values):
            stocks_data["CASH"] = {"name": "💵 Cash", "values": cash_values}

    # Sortiere nach durchschnittlichem Wert (größte zuerst)
    sorted_stocks = dict(sorted(
        stocks_data.items(),
        key=lambda x: sum(x[1]["values"]) / max(len(x[1]["values"]), 1),
        reverse=True,
    ))

    return {
        "dates": dates,
        "stocks": sorted_stocks,
        "total": [round(v, 2) for v in total_values],
        "total_cost": cost_timeline,
    }


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _reconstruct_cost_timeline(activities: list[dict], dates: list[str]) -> list[float]:
    """Rekonstruiert die kumulierten Einstandskosten pro Tag."""
    cost_events: list[tuple[str, float]] = []
    cumulative = 0.0

    sorted_acts = sorted(activities, key=lambda a: a.get("date", ""))
    for act in sorted_acts:
        act_type = (act.get("type") or "").lower()
        date = act.get("date", "")
        amount = float(act.get("amount") or 0)
        ticker = act.get("ticker", "")

        if not date or ticker == "CASH":
            continue

        if act_type in ("buy", "kauf", "purchase", "transferin", "transfer_in"):
            cumulative += amount
        elif act_type in ("sell", "verkauf", "sale", "transferout", "transfer_out"):
            cumulative -= amount

        cost_events.append((date, cumulative))

    result = []
    for date_str in dates:
        cost = 0.0
        for event_date, event_cost in cost_events:
            if event_date <= date_str:
                cost = event_cost
            else:
                break
        result.append(round(cost, 2))

    return result


async def _fetch_prices_with_cache(
    tickers: list[str],
    start_date: str,
    end_date: str,
) -> dict[str, dict[str, float]]:
    """Inkrementeller Kursabruf mit SQLite-Cache.

    1. Gecachte Kurse laden
    2. Pro Ticker prüfen: Welche Tage fehlen?
    3. Nur fehlende Tage von yfinance nachladen
    4. Neue Kurse in Cache speichern
    """
    from state import YFINANCE_ALIASES

    if not tickers:
        return {}

    # Ticker→yfinance Mapping (ISINs überspringen)
    ticker_to_yf = {}
    yf_to_ticker = {}
    skip_tickers = set()

    for t in tickers:
        yf_t = YFINANCE_ALIASES.get(t, t)
        if len(yf_t) == 12 and yf_t[:2].isalpha():
            skip_tickers.add(t)
            continue
        ticker_to_yf[t] = yf_t
        yf_to_ticker[yf_t] = t

    if not ticker_to_yf:
        return {}

    valid_tickers = list(ticker_to_yf.keys())

    # 1. Gecachte Kurse laden
    cached = _load_cached_prices(valid_tickers)
    cached_count = sum(len(v) for v in cached.values())

    # 2. Bestimmen was nachgeladen werden muss
    # Pro Ticker: ab wann fehlen Daten?
    tickers_to_fetch: dict[str, str] = {}  # yf_ticker → fetch_from_date
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    for orig_t, yf_t in ticker_to_yf.items():
        if orig_t in cached and cached[orig_t]:
            last_cached = max(cached[orig_t].keys())
            if last_cached >= yesterday:
                # Schon up-to-date → nur heute nachladen
                fetch_from = yesterday
            else:
                # Ab dem Tag nach dem letzten Cache nachladen
                last_dt = datetime.strptime(last_cached, "%Y-%m-%d")
                fetch_from = (last_dt + timedelta(days=1)).strftime("%Y-%m-%d")
            tickers_to_fetch[yf_t] = fetch_from
        else:
            # Gar nicht gecacht → alles laden
            tickers_to_fetch[yf_t] = start_date

    # 3. Fehlende Daten von yfinance holen
    if tickers_to_fetch:
        # Gruppiere nach fetch_from_date um Batch-Downloads zu optimieren
        # Einfachster Ansatz: Lade ab dem frühesten fehlenden Datum für alle
        earliest_fetch = min(tickers_to_fetch.values())

        # Prüfe ob ein Fetch überhaupt nötig ist
        if earliest_fetch <= end_date:
            yf_tickers = list(tickers_to_fetch.keys())
            logger.info(
                f"📊 Historie: {cached_count} Kurse aus Cache, "
                f"lade {len(yf_tickers)} Ticker ab {earliest_fetch}"
            )
            new_prices = await _fetch_from_yfinance(
                yf_tickers, yf_to_ticker, earliest_fetch, end_date
            )

            if new_prices:
                # In Cache speichern
                _save_prices_to_cache(new_prices)

                # Mit gecachten Daten mergen
                for ticker, date_prices in new_prices.items():
                    if ticker not in cached:
                        cached[ticker] = {}
                    cached[ticker].update(date_prices)
        else:
            logger.info(f"📊 Historie: Alle {cached_count} Kurse aus Cache geladen (aktuell)")
    else:
        logger.info(f"📊 Historie: Alle {cached_count} Kurse aus Cache geladen")

    return cached


async def _fetch_from_yfinance(
    yf_tickers: list[str],
    yf_to_ticker: dict[str, str],
    start_date: str,
    end_date: str,
) -> dict[str, dict[str, float]]:
    """Lädt historische Kurse via yfinance Batch-Download.

    Returns: {original_ticker: {date: close, ...}, ...}
    """
    if not yf_tickers:
        return {}

    try:
        import yfinance as yf

        data = yf.download(
            tickers=yf_tickers,
            start=start_date,
            end=end_date,
            interval="1d",
            progress=False,
            group_by="ticker" if len(yf_tickers) > 1 else "column",
        )

        if data is None or data.empty:
            logger.warning("yfinance download returned empty data")
            return {}

        result: dict[str, dict[str, float]] = {}

        if len(yf_tickers) == 1:
            yf_t = yf_tickers[0]
            orig_ticker = yf_to_ticker.get(yf_t, yf_t)
            if "Close" in data.columns:
                closes = data["Close"].dropna()
                result[orig_ticker] = {
                    idx.strftime("%Y-%m-%d"): round(float(val), 4)
                    for idx, val in closes.items()
                }
        else:
            for yf_t in yf_tickers:
                orig_ticker = yf_to_ticker.get(yf_t, yf_t)
                try:
                    if yf_t in data.columns.get_level_values(0):
                        closes = data[yf_t]["Close"].dropna()
                        result[orig_ticker] = {
                            idx.strftime("%Y-%m-%d"): round(float(val), 4)
                            for idx, val in closes.items()
                        }
                except Exception as e:
                    logger.debug(f"Historie-Preis für {yf_t} fehlgeschlagen: {e}")

        new_count = sum(len(v) for v in result.values())
        logger.info(f"📊 yfinance: {new_count} neue Kurse für {len(result)}/{len(yf_tickers)} Ticker")
        return result

    except Exception as e:
        logger.error(f"yfinance batch download fehlgeschlagen: {e}")
        return {}
