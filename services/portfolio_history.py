"""FinanceBro - Portfolio History Service.

Verwaltet historische Portfolio-Snapshots:
- Backfill via Parqet Connect API (komplette Historie)
- Tägliches Update (append/upsert)
- Persistenz in Google Cloud Storage (+ lokaler Cache)
- Schnelle YTD/Performance-Berechnung aus lokalen Daten
"""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)

HISTORY_FILE = Path(settings.CACHE_DIR) / "portfolio_history.json"
GCS_BLOB_NAME = "portfolio_history.json"


def _load_local() -> dict:
    """Lädt History aus lokalem Cache."""
    if HISTORY_FILE.exists():
        try:
            data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "daily" in data:
                return data
        except Exception as e:
            logger.warning(f"History Cache korrupt: {e}")
    return {"metadata": {}, "daily": []}


def _save_local(data: dict):
    """Speichert History in lokalen Cache."""
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        HISTORY_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=None),
            encoding="utf-8"
        )
    except Exception as e:
        logger.warning(f"History lokal speichern fehlgeschlagen: {e}")


def _upload_to_gcs(data: dict):
    """Lädt History nach Google Cloud Storage hoch."""
    if not settings.GCS_BUCKET_NAME or not settings.GCP_PROJECT_ID:
        return
    try:
        from google.cloud import storage
        client = storage.Client(project=settings.GCP_PROJECT_ID)
        bucket = client.bucket(settings.GCS_BUCKET_NAME)
        blob = bucket.blob(GCS_BLOB_NAME)
        blob.upload_from_string(
            json.dumps(data, ensure_ascii=False),
            content_type="application/json"
        )
        logger.info(f"📤 History nach GCS hochgeladen ({len(data['daily'])} Tage)")
    except Exception as e:
        logger.warning(f"GCS Upload fehlgeschlagen: {e}")


def _download_from_gcs() -> Optional[dict]:
    """Lädt History von Google Cloud Storage."""
    if not settings.GCS_BUCKET_NAME or not settings.GCP_PROJECT_ID:
        return None
    try:
        from google.cloud import storage
        client = storage.Client(project=settings.GCP_PROJECT_ID)
        bucket = client.bucket(settings.GCS_BUCKET_NAME)
        blob = bucket.blob(GCS_BLOB_NAME)
        if not blob.exists():
            return None
        content = blob.download_as_text(encoding="utf-8")
        data = json.loads(content)
        if isinstance(data, dict) and "daily" in data:
            logger.info(f"📥 History von GCS geladen ({len(data['daily'])} Tage)")
            return data
    except Exception as e:
        logger.debug(f"GCS Download fehlgeschlagen: {e}")
    return None


def load_history() -> dict:
    """Lädt History: Lokal → GCS → Leer.
    
    Beim Start auf Cloud Run ist der lokale Cache leer,
    dann wird aus GCS geladen und lokal gecacht.
    """
    data = _load_local()
    if data["daily"]:
        return data
    
    # Lokaler Cache leer → GCS versuchen
    gcs_data = _download_from_gcs()
    if gcs_data and gcs_data.get("daily"):
        _save_local(gcs_data)  # Lokal cachen
        return gcs_data
    
    return {"metadata": {}, "daily": []}


def save_history(data: dict):
    """Speichert History lokal + GCS."""
    # Metadata aktualisieren
    if data["daily"]:
        data["metadata"] = {
            "first_date": data["daily"][0]["date"],
            "last_date": data["daily"][-1]["date"],
            "total_days": len(data["daily"]),
            "last_updated": datetime.now().isoformat(),
            "source": "parqet_connect_api",
        }
    _save_local(data)
    _upload_to_gcs(data)


def get_ytd() -> Optional[float]:
    """Berechnet Portfolio YTD aus gespeicherter History."""
    data = load_history()
    if not data["daily"]:
        return None
    
    year_start = f"{datetime.now().year}-01-01"
    
    # Finde den Datenpunkt am/nach 1. Januar
    jan_entry = None
    for entry in data["daily"]:
        if entry["date"] >= year_start:
            jan_entry = entry
            break
    
    if not jan_entry:
        return None
    
    # Letzter Eintrag = aktueller Wert
    latest = data["daily"][-1]
    
    start_val = jan_entry["total_value"]
    end_val = latest["total_value"]
    
    if start_val > 0 and end_val > 0:
        return round(((end_val - start_val) / start_val) * 100, 2)
    
    return None


def get_history_range(period: str = "ytd") -> list[dict]:
    """Gibt History für einen Zeitraum zurück.
    
    Args:
        period: ytd, 1m, 3m, 6m, 1y, max
    """
    data = load_history()
    if not data["daily"]:
        return []
    
    daily = data["daily"]
    now = datetime.now()
    
    if period == "max":
        return daily
    elif period == "ytd":
        year_start = f"{now.year}-01-01"
        return [d for d in daily if d["date"] >= year_start]
    else:
        # Parse period: 1m, 3m, 6m, 1y
        multiplier = int(period[:-1])
        unit = period[-1]
        if unit == "m":
            start_date = now - timedelta(days=multiplier * 30)
        elif unit == "y":
            start_date = now - timedelta(days=multiplier * 365)
        else:
            return daily
        
        start_str = start_date.strftime("%Y-%m-%d")
        return [d for d in daily if d["date"] >= start_str]


async def backfill_from_parqet() -> int:
    """Einmaliger Backfill aller historischen Daten via Parqet Performance Chart API.
    
    Returns: Anzahl der gespeicherten Datenpunkte.
    """
    from fetchers.parqet import fetch_portfolio_performance_chart
    
    logger.info("📊 Starte Backfill über Parqet Performance Chart API...")
    try:
        chart_points = await fetch_portfolio_performance_chart(timeframe="max")
        if not chart_points:
            logger.warning("Backfill: Keine Chart-Daten von Parqet erhalten")
            return 0
        
        snapshots = []
        for entry in chart_points:
            date_str = entry.get("date", "")
            if not date_str:
                continue
            
            # Format date as YYYY-MM-DD
            if "T" in date_str:
                date_str = date_str.split("T")[0]
            elif " " in date_str:
                date_str = date_str.split(" ")[0]
            
            val = entry.get("totalValue", 0)
            if val > 0:
                snapshots.append({
                    "date": date_str,
                    "total_value": round(val, 2)
                })
        
        # Deduplizieren und sortieren
        seen = set()
        unique_snapshots = []
        for s in sorted(snapshots, key=lambda x: x["date"]):
            if s["date"] not in seen:
                seen.add(s["date"])
                unique_snapshots.append(s)
        
        if unique_snapshots:
            history = {"metadata": {}, "daily": unique_snapshots}
            save_history(history)
            logger.info(f"✅ Backfill abgeschlossen: {len(unique_snapshots)} Datenpunkte gespeichert")
            return len(unique_snapshots)
        
    except Exception as e:
        logger.error(f"Backfill fehlgeschlagen: {e}")
    
    return 0


async def update_today():
    """Fügt heutigen Snapshot hinzu (oder aktualisiert ihn).
    
    Nutzt Parqet Connect API für den aktuellen Portfoliowert.
    Wird täglich vom Scheduler aufgerufen.
    """
    from fetchers.parqet import _ensure_valid_token, PARQET_CONNECT_API
    import httpx
    
    access_token = await _ensure_valid_token()
    if not access_token or not settings.PARQET_PORTFOLIO_ID:
        return
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"{PARQET_CONNECT_API}/performance"
    body = {
        "portfolioIds": [settings.PARQET_PORTFOLIO_ID],
        "interval": {"type": "relative", "value": "ytd"}
    }
    
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, headers=headers, json=body)
            if resp.status_code != 200:
                logger.warning(f"History Update: Parqet API {resp.status_code}")
                return
            
            data = resp.json()
            perf = data.get("performance", {})
            val = perf.get("valuation", {})
            end_val = val.get("atIntervalEnd", 0)
            
            if end_val <= 0:
                return
            
            # History laden und updaten
            history = load_history()
            
            # Upsert: heute aktualisieren oder anhängen
            today_entry = {
                "date": today_str,
                "total_value": round(end_val, 2),
            }
            
            # Existierenden Eintrag für heute ersetzen
            found = False
            for i, entry in enumerate(history["daily"]):
                if entry["date"] == today_str:
                    history["daily"][i] = today_entry
                    found = True
                    break
            
            if not found:
                history["daily"].append(today_entry)
                # Sortieren (falls out-of-order)
                history["daily"].sort(key=lambda x: x["date"])
            
            save_history(history)
            logger.info(f"📸 History Update: {today_str} — €{end_val:,.2f}")
            
    except Exception as e:
        logger.warning(f"History Update fehlgeschlagen: {e}")
