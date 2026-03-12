"""FinanzBro - SQLite Persistence Layer

Ersetzt JSON-Dateien für persistente Daten:
  - Portfolio-Snapshots (tägliche Werte)
  - Score-History (Ticker-Scores pro Analyse)

Datenbank: cache/finanzbro.db
Für Cloud Run Persistenz: Litestream → GCS Backup.
"""
import json
import logging
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from config import settings

logger = logging.getLogger(__name__)

TZ_BERLIN = ZoneInfo("Europe/Berlin")

DB_PATH = settings.CACHE_DIR / "finanzbro.db"

# Thread-local connections (sqlite3 ist nicht thread-safe)
_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    """Gibt eine Thread-lokale SQLite-Verbindung zurück."""
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(str(DB_PATH), timeout=10)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA synchronous=NORMAL")
    return _local.conn


def init_db():
    """Erstellt Tabellen falls sie nicht existieren."""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS portfolio_snapshots (
            date TEXT PRIMARY KEY,
            total_value REAL NOT NULL,
            total_cost REAL NOT NULL,
            total_pnl REAL NOT NULL,
            num_positions INTEGER NOT NULL,
            eur_usd_rate REAL DEFAULT 1.0,
            timestamp TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS score_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            ticker TEXT NOT NULL,
            score REAL NOT NULL,
            rating TEXT NOT NULL,
            confidence REAL DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_score_ticker ON score_history(ticker);
        CREATE INDEX IF NOT EXISTS idx_score_timestamp ON score_history(timestamp);

        CREATE TABLE IF NOT EXISTS analysis_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            level TEXT NOT NULL,
            portfolio_score REAL NOT NULL,
            portfolio_rating TEXT NOT NULL,
            num_positions INTEGER NOT NULL,
            avg_confidence REAL DEFAULT 0
        );
    """)
    conn.commit()
    logger.info(f"📦 SQLite-Datenbank initialisiert: {DB_PATH}")


# ─── Portfolio Snapshots ────────────────────────────────────

def save_snapshot(
    total_value: float,
    total_cost: float,
    total_pnl: float,
    num_positions: int,
    eur_usd_rate: float = 1.0,
):
    """Speichert einen täglichen Portfolio-Snapshot (UPSERT)."""
    today = datetime.now(tz=TZ_BERLIN).strftime("%Y-%m-%d")
    ts = datetime.now(tz=TZ_BERLIN).isoformat()

    conn = _get_conn()
    conn.execute(
        """INSERT INTO portfolio_snapshots (date, total_value, total_cost, total_pnl, num_positions, eur_usd_rate, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(date) DO UPDATE SET
             total_value=excluded.total_value,
             total_cost=excluded.total_cost,
             total_pnl=excluded.total_pnl,
             num_positions=excluded.num_positions,
             eur_usd_rate=excluded.eur_usd_rate,
             timestamp=excluded.timestamp""",
        (today, round(total_value, 2), round(total_cost, 2),
         round(total_pnl, 2), num_positions, eur_usd_rate, ts),
    )
    conn.commit()
    logger.info(f"📸 Snapshot gespeichert: {today} — €{total_value:,.2f}")


def load_snapshots(days: int = 90) -> list[dict]:
    """Lädt historische Portfolio-Snapshots."""
    conn = _get_conn()
    if days > 0:
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        rows = conn.execute(
            "SELECT * FROM portfolio_snapshots WHERE date >= ? ORDER BY date",
            (cutoff,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM portfolio_snapshots ORDER BY date"
        ).fetchall()

    return [dict(r) for r in rows]


# ─── Score History ──────────────────────────────────────────

def save_scores(timestamp: str, scores: dict[str, dict]):
    """Speichert Score-Snapshot für alle Ticker.

    Args:
        timestamp: ISO timestamp der Analyse
        scores: {ticker: {score, rating, confidence}}
    """
    conn = _get_conn()
    rows = [
        (timestamp, ticker, data["score"], data["rating"], data.get("confidence", 0))
        for ticker, data in scores.items()
    ]
    conn.executemany(
        "INSERT INTO score_history (timestamp, ticker, score, rating, confidence) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def save_analysis_report(
    timestamp: str,
    level: str,
    portfolio_score: float,
    portfolio_rating: str,
    num_positions: int,
    avg_confidence: float,
    scores: dict[str, dict],
):
    """Speichert einen kompletten Analyse-Report (Report-Metadaten + Ticker-Scores)."""
    conn = _get_conn()
    conn.execute(
        """INSERT INTO analysis_reports (timestamp, level, portfolio_score, portfolio_rating, num_positions, avg_confidence)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (timestamp, level, portfolio_score, portfolio_rating, num_positions, avg_confidence),
    )
    save_scores(timestamp, scores)
    conn.commit()
    logger.info(f"📊 Analyse-Report gespeichert: Score {portfolio_score:.1f} ({portfolio_rating})")


def get_analysis_history(days: int = 30) -> list[dict]:
    """Liest Analyse-History inkl. Scores.

    Rückgabe-Format kompatibel mit dem bisherigen JSON-Format:
    [{timestamp, level, portfolio_score, portfolio_rating, scores: {ticker: {score, rating, confidence}}}]
    """
    conn = _get_conn()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    reports = conn.execute(
        "SELECT * FROM analysis_reports WHERE timestamp >= ? ORDER BY timestamp",
        (cutoff,),
    ).fetchall()

    result = []
    for r in reports:
        # Scores für diesen Timestamp laden
        scores_rows = conn.execute(
            "SELECT ticker, score, rating, confidence FROM score_history WHERE timestamp = ?",
            (r["timestamp"],),
        ).fetchall()

        scores = {
            s["ticker"]: {"score": s["score"], "rating": s["rating"], "confidence": s["confidence"]}
            for s in scores_rows
        }

        result.append({
            "timestamp": r["timestamp"],
            "level": r["level"],
            "portfolio_score": r["portfolio_score"],
            "portfolio_rating": r["portfolio_rating"],
            "num_positions": r["num_positions"],
            "avg_confidence": r["avg_confidence"],
            "scores": scores,
        })

    return result


def get_score_trend(ticker: str, days: int = 7) -> list[dict]:
    """Score-Verlauf für einen einzelnen Ticker."""
    conn = _get_conn()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    rows = conn.execute(
        "SELECT timestamp, score, rating FROM score_history WHERE ticker = ? AND timestamp >= ? ORDER BY timestamp",
        (ticker, cutoff),
    ).fetchall()

    return [dict(r) for r in rows]


def get_latest_scores() -> dict[str, float]:
    """Holt die neuesten Scores pro Ticker."""
    conn = _get_conn()
    rows = conn.execute(
        """SELECT ticker, score FROM score_history
           WHERE timestamp = (SELECT MAX(timestamp) FROM score_history)""",
    ).fetchall()

    return {r["ticker"]: r["score"] for r in rows}


# ─── Migration: JSON → SQLite ──────────────────────────────

def migrate_json_to_sqlite():
    """Importiert bestehende JSON-History-Dateien in SQLite (einmalig)."""
    migrated = 0

    # 1. Portfolio-Snapshots
    history_file = settings.CACHE_DIR / "portfolio_history.json"
    if history_file.exists():
        try:
            data = json.loads(history_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for entry in data:
                    try:
                        save_snapshot(
                            total_value=entry.get("total_value", 0),
                            total_cost=entry.get("total_cost", 0),
                            total_pnl=entry.get("total_pnl", 0),
                            num_positions=entry.get("num_positions", 0),
                            eur_usd_rate=entry.get("eur_usd_rate", 1.0),
                        )
                        migrated += 1
                    except Exception:
                        pass
            # Rename to .bak after successful migration
            history_file.rename(history_file.with_suffix(".json.bak"))
            logger.info(f"📦 {migrated} Portfolio-Snapshots von JSON migriert")
        except Exception as e:
            logger.warning(f"JSON-Migration Portfolio fehlgeschlagen: {e}")

    # 2. Analysis History
    analysis_file = settings.CACHE_DIR / "analysis_history.json"
    if analysis_file.exists():
        try:
            data = json.loads(analysis_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for entry in data:
                    try:
                        save_analysis_report(
                            timestamp=entry.get("timestamp", ""),
                            level=entry.get("level", "full"),
                            portfolio_score=entry.get("portfolio_score", 50),
                            portfolio_rating=entry.get("portfolio_rating", "hold"),
                            num_positions=entry.get("num_positions", 0),
                            avg_confidence=entry.get("avg_confidence", 0),
                            scores=entry.get("scores", {}),
                        )
                        migrated += 1
                    except Exception:
                        pass
            analysis_file.rename(analysis_file.with_suffix(".json.bak"))
            logger.info(f"📦 Analysis-History von JSON migriert")
        except Exception as e:
            logger.warning(f"JSON-Migration Analysis fehlgeschlagen: {e}")

    return migrated


# Automatisch Tabellen erstellen beim Import
init_db()
