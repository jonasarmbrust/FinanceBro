"""FinanceBro - TipRanks MCP Fetcher

Kommuniziert mit dem TipRanks MCP-Server (https://mcp.tipranks.com/mcp/)
über das MCP-Protokoll (JSON-RPC über Streamable HTTP / SSE Transport).

Features:
  - MCP Session-Management (initialize → notifications/initialized → tools/call)
  - SSE Response Parsing (Server antwortet mit text/event-stream)
  - Rate Limiting (pro Minute + pro Tag)
  - CacheManager-Integration (6h TTL)
  - Graceful Degradation bei Fehlern

Authentifizierung via API-Key als Query-Parameter.
"""
import asyncio
import json
import logging
import re
import time
from typing import Any, Optional

import httpx

from cache_manager import CacheManager
from config import settings

logger = logging.getLogger(__name__)

# Cache mit 6h TTL für TipRanks-Daten
_cache = CacheManager("tipranks", ttl_hours=6)

# MCP Session State
_session_id: Optional[str] = None
_session_lock = asyncio.Lock()

# Rate Limiting State
_request_times: list[float] = []   # Timestamps der letzten Requests
_daily_count: int = 0              # Täglicher Request-Zähler
_daily_reset: float = 0.0         # Zeitpunkt des nächsten Daily-Resets

# JSON-RPC Request ID Counter
_rpc_id: int = 0


def _next_rpc_id() -> int:
    """Nächste JSON-RPC Request-ID."""
    global _rpc_id
    _rpc_id += 1
    return _rpc_id


def _check_rate_limit() -> bool:
    """Prüft ob ein Request innerhalb der Rate Limits liegt.

    Returns:
        True wenn Request erlaubt, False wenn Limit erreicht.
    """
    global _daily_count, _daily_reset

    now = time.time()

    # Daily Reset (alle 24h)
    if now > _daily_reset:
        _daily_count = 0
        _daily_reset = now + 86400  # 24h

    # Daily Limit
    if _daily_count >= settings.TIPRANKS_DAILY_LIMIT:
        logger.warning(
            f"TipRanks Daily-Limit erreicht ({_daily_count}/{settings.TIPRANKS_DAILY_LIMIT})"
        )
        return False

    # Per-Minute Limit (Sliding Window)
    cutoff = now - 60
    _request_times[:] = [t for t in _request_times if t > cutoff]
    if len(_request_times) >= settings.TIPRANKS_RPM_LIMIT:
        logger.debug(
            f"TipRanks RPM-Limit erreicht ({len(_request_times)}/{settings.TIPRANKS_RPM_LIMIT})"
        )
        return False

    return True


def _record_request():
    """Vermerkt einen erfolgreichen Request für Rate Limiting."""
    global _daily_count
    _request_times.append(time.time())
    _daily_count += 1


def _get_base_url() -> str:
    """MCP Server URL mit API-Key."""
    return f"https://mcp.tipranks.com/mcp/?apikey={settings.TIPRANKS_API_KEY}"


# ─── MCP Streamable HTTP Headers ────────────────────────────
_MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


def _parse_sse_response(text: str) -> Optional[dict]:
    """Parsed eine SSE-Response (text/event-stream) und extrahiert den JSON-Body.

    TipRanks MCP antwortet im SSE-Format:
        event: message
        data: {"jsonrpc":"2.0","id":1,"result":{...}}

    Kann mehrere Events enthalten — wir nehmen das letzte mit 'data:'.
    """
    last_data = None
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            last_data = line[6:]  # Strip "data: " prefix
        elif line.startswith("data:"):
            last_data = line[5:]

    if last_data:
        try:
            return json.loads(last_data)
        except json.JSONDecodeError as e:
            logger.error(f"TipRanks SSE JSON-Parse-Fehler: {e}")
    return None


def _parse_response(resp: httpx.Response) -> Optional[dict]:
    """Parsed die HTTP-Response — unterstützt JSON und SSE."""
    content_type = resp.headers.get("content-type", "")

    if "text/event-stream" in content_type:
        return _parse_sse_response(resp.text)
    elif "application/json" in content_type:
        try:
            return resp.json()
        except json.JSONDecodeError:
            return None

    # Fallback: Versuche beide Formate
    try:
        return resp.json()
    except Exception:
        return _parse_sse_response(resp.text)


async def _initialize_session(client: httpx.AsyncClient) -> Optional[str]:
    """Initialisiert eine MCP-Session und gibt die Session-ID zurück.

    Sendet einen JSON-RPC `initialize` Request an den MCP-Server.
    Die Session-ID wird aus dem Response-Header `Mcp-Session-Id` extrahiert.
    Danach wird `notifications/initialized` gesendet (MCP-Protokoll-Pflicht).
    """
    payload = {
        "jsonrpc": "2.0",
        "id": _next_rpc_id(),
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {
                "name": "FinanceBro",
                "version": "1.0",
            },
        },
    }

    try:
        resp = await client.post(
            _get_base_url(),
            json=payload,
            headers=_MCP_HEADERS,
            timeout=15.0,
        )
        resp.raise_for_status()

        # Session-ID aus Header
        session_id = resp.headers.get("Mcp-Session-Id") or resp.headers.get("mcp-session-id")

        # Fallback: Session-ID aus Response-Body parsen (bei SSE)
        if not session_id:
            body = _parse_response(resp)
            if body and "error" in body:
                logger.error(f"TipRanks MCP initialize Fehler: {body['error']}")
                return None
            # Manche Server liefern Session-ID nur im Header — ohne ID können wir
            # trotzdem fortfahren wenn der Server es erlaubt
            logger.info("TipRanks MCP: Keine Session-ID — versuche sessionless Modus")
            return "__sessionless__"

        logger.info(f"TipRanks MCP Session initialisiert: {session_id[:16]}...")

        # MCP-Pflicht: notifications/initialized senden
        try:
            await client.post(
                _get_base_url(),
                json={
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                },
                headers={
                    **_MCP_HEADERS,
                    "Mcp-Session-Id": session_id,
                },
                timeout=10.0,
            )
        except Exception:
            pass  # Notification ist best-effort

        return session_id

    except httpx.HTTPStatusError as e:
        logger.error(
            f"TipRanks MCP initialize HTTP-Fehler: {e.response.status_code} — "
            f"{e.response.text[:200]}"
        )
        return None
    except Exception as e:
        logger.error(f"TipRanks MCP initialize fehlgeschlagen: {e}")
        return None


async def _ensure_session(client: httpx.AsyncClient) -> Optional[str]:
    """Stellt sicher, dass eine aktive MCP-Session existiert."""
    global _session_id

    async with _session_lock:
        if _session_id is None:
            _session_id = await _initialize_session(client)
        return _session_id


async def _call_tool(
    client: httpx.AsyncClient,
    tool_name: str,
    arguments: dict[str, Any],
    session_id: str,
) -> Optional[dict]:
    """Ruft ein MCP-Tool auf und gibt das Ergebnis zurück.

    Args:
        client: httpx AsyncClient
        tool_name: Name des MCP-Tools (z.B. "get_assets_data")
        arguments: Tool-Argumente
        session_id: Aktive MCP-Session-ID

    Returns:
        Parsed JSON-Daten aus result.content[0].text oder None bei Fehler.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": _next_rpc_id(),
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
        },
    }

    headers = {**_MCP_HEADERS}
    if session_id and session_id != "__sessionless__":
        headers["Mcp-Session-Id"] = session_id

    try:
        resp = await client.post(
            _get_base_url(),
            json=payload,
            headers=headers,
            timeout=30.0,
        )

        # HTTP 429 — Rate Limited, Retry-After respektieren
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "60"))
            logger.warning(f"TipRanks API 429 — Retry nach {retry_after}s")
            await asyncio.sleep(min(retry_after, 120))
            # Einmaliger Retry
            resp = await client.post(
                _get_base_url(), json=payload, headers=headers, timeout=30.0
            )

        resp.raise_for_status()

        # Response parsen (JSON oder SSE)
        body = _parse_response(resp)
        if not body:
            logger.warning(f"TipRanks MCP: Unparseable Response für {tool_name}")
            return None

        if "error" in body:
            logger.error(f"TipRanks MCP Tool-Fehler ({tool_name}): {body['error']}")
            return None

        # Ergebnis extrahieren: result.content[0].text → JSON-String
        result = body.get("result", {})
        content = result.get("content", [])
        if content and isinstance(content, list) and len(content) > 0:
            text_data = content[0].get("text", "")
            if text_data:
                try:
                    return json.loads(text_data)
                except json.JSONDecodeError:
                    # Manche Tools liefern reinen Text statt JSON
                    logger.debug(f"TipRanks {tool_name}: Text statt JSON — {text_data[:200]}")
                    return {"_raw_text": text_data}

        logger.warning(f"TipRanks MCP: Leeres Ergebnis für {tool_name}")
        return None

    except httpx.HTTPStatusError as e:
        # Session abgelaufen? Reset und Retry
        if e.response.status_code in (401, 403):
            logger.warning(f"TipRanks Session abgelaufen — Reset")
            reset_session()
        logger.error(f"TipRanks MCP HTTP-Fehler ({tool_name}): {e.response.status_code}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"TipRanks MCP JSON-Parse-Fehler ({tool_name}): {e}")
        return None
    except Exception as e:
        logger.error(f"TipRanks MCP Tool-Call fehlgeschlagen ({tool_name}): {e}")
        return None


async def fetch_tipranks_data(ticker: str) -> Optional["TipRanksData"]:
    """Lädt TipRanks-Daten für einen einzelnen Ticker.

    Nutzt den MCP-Server um Smart Score, Analyst-Daten, Insider-Trends,
    Hedge-Fund-Aktivität und Sentiment abzurufen.

    Args:
        ticker: Aktien-Ticker (z.B. "AAPL")

    Returns:
        TipRanksData-Objekt oder None bei Fehler/Rate-Limit.
    """
    from models import TipRanksData

    # Cache prüfen
    cache_key = f"tipranks_{ticker}"
    cached = _cache.get(cache_key)
    if cached is not None:
        try:
            return TipRanksData(**cached)
        except Exception:
            pass  # Cache-Daten ungültig → neu laden

    # Rate Limit prüfen
    if not _check_rate_limit():
        logger.debug(f"TipRanks: Rate-Limit für {ticker} — überspringe")
        return None

    async with httpx.AsyncClient() as client:
        # Session sicherstellen
        session_id = await _ensure_session(client)
        if not session_id:
            logger.warning("TipRanks: Keine MCP-Session — überspringe")
            return None

        # Request vermerken
        _record_request()

        # MCP Tool aufrufen
        raw = await _call_tool(
            client,
            tool_name="get_assets_data",
            arguments={"tickers": ticker},
            session_id=session_id,
        )

        if not raw:
            return None

    try:
        tipranks = _parse_tipranks_response(raw, ticker)
        if tipranks:
            _cache.set(cache_key, tipranks.model_dump())
            logger.info(
                f"TipRanks {ticker}: Smart Score {tipranks.smart_score}/10, "
                f"Konsens: {tipranks.analyst_consensus}"
            )
        return tipranks
    except Exception as e:
        logger.warning(f"TipRanks Parsing fehlgeschlagen für {ticker}: {e}")
        return None


async def fetch_tipranks_batch(tickers: list[str]) -> dict[str, "TipRanksData"]:
    """Lädt TipRanks-Daten für mehrere Ticker (Batch-Optimierung).

    Nutzt die Batch-Fähigkeit des MCP-Tools (kommaseparierte Ticker).
    Fallback auf Einzel-Requests wenn Batch fehlschlägt.

    Args:
        tickers: Liste von Ticker-Symbolen

    Returns:
        Dict mit Ticker → TipRanksData Mapping
    """
    from models import TipRanksData

    results: dict[str, TipRanksData] = {}

    # Bereits gecachte Ticker sammeln
    uncached: list[str] = []
    for t in tickers:
        cache_key = f"tipranks_{t}"
        cached = _cache.get(cache_key)
        if cached is not None:
            try:
                results[t] = TipRanksData(**cached)
                continue
            except Exception:
                pass
        uncached.append(t)

    if not uncached:
        return results

    # Rate Limit für Batch
    if not _check_rate_limit():
        logger.debug("TipRanks: Rate-Limit für Batch — nur Cache-Daten")
        return results

    async with httpx.AsyncClient() as client:
        session_id = await _ensure_session(client)
        if not session_id:
            return results

        _record_request()

        # Batch-Request (kommaseparierte Ticker)
        tickers_str = ",".join(uncached)
        raw = await _call_tool(
            client,
            tool_name="get_assets_data",
            arguments={"tickers": tickers_str},
            session_id=session_id,
        )

        if raw:
            # Ergebnis kann ein Dict pro Ticker oder eine Liste sein
            for t in uncached:
                try:
                    parsed = _parse_tipranks_response(raw, t)
                    if parsed:
                        results[t] = parsed
                        _cache.set(f"tipranks_{t}", parsed.model_dump())
                except Exception as e:
                    logger.debug(f"TipRanks Batch-Parse für {t}: {e}")

    return results


def _parse_tipranks_response(raw: dict, ticker: str) -> Optional["TipRanksData"]:
    """Parsed die TipRanks MCP-Antwort in ein TipRanksData-Objekt.

    TipRanks API liefert: {"assetsData": [{"ticker": "AAPL", "smartScore": 9, ...}]}
    Felder sind flach (nicht verschachtelt).
    """
    from models import TipRanksData

    # Wenn raw ein _raw_text Fallback ist, können wir nichts parsen
    if "_raw_text" in raw:
        logger.debug(f"TipRanks {ticker}: Nur Text-Response verfügbar")
        return None

    # Daten aus assetsData-Array extrahieren
    data = None
    assets = raw.get("assetsData") or raw.get("assets_data") or []

    if isinstance(assets, list):
        # Ticker im Array suchen
        for asset in assets:
            if isinstance(asset, dict):
                asset_ticker = asset.get("ticker", "").upper()
                if asset_ticker == ticker.upper():
                    data = asset
                    break
        # Fallback: Erstes Element bei Einzel-Ticker-Request
        if data is None and len(assets) == 1 and isinstance(assets[0], dict):
            data = assets[0]

    # Fallback: Direkte Daten (ohne assetsData-Wrapper)
    if data is None:
        if ticker in raw:
            data = raw[ticker]
        elif ticker.upper() in raw:
            data = raw[ticker.upper()]
        elif "smartScore" in raw or "smart_score" in raw:
            data = raw  # Direkt die Daten

    if not data or not isinstance(data, dict):
        logger.debug(f"TipRanks {ticker}: Keine Daten in Response (keys: {list(raw.keys())[:5]})")
        return None

    # Smart Score extrahieren (Pflichtfeld)
    smart_score = data.get("smartScore") or data.get("smart_score")
    if smart_score is None:
        logger.debug(f"TipRanks {ticker}: Kein Smart Score in Response")
        return None

    smart_score = max(1, min(10, int(smart_score)))

    # Analyst Consensus (TipRanks liefert direkt als String: "Buy", "Hold", "Sell")
    consensus_str = data.get("analystConsensus") or data.get("analyst_consensus") or ""
    best_consensus = data.get("bestAnalystConsensus") or ""

    # TipRanks liefert keine Buy/Hold/Sell Counts im get_assets_data Endpoint
    # Setze 0 als Default — detaillierte Daten kämen über get_analyst_ratings
    buy = 0
    hold = 0
    sell = 0
    analyst_count = 0

    # Preisziel (TipRanks liefert als einzelne Zahl, nicht verschachtelt)
    pt_avg = float(data.get("priceTarget") or data.get("price_target") or 0)

    # Upside (TipRanks liefert als Dezimalzahl, z.B. 0.1139 = 11.39%)
    upside_raw = data.get("priceTargetUpside") or data.get("upside_potential") or 0
    upside = float(upside_raw)
    if abs(upside) < 5:  # Dezimalformat (0.11 = 11%)
        upside = upside * 100

    # Hedge Fund Score (0-1 Skala)
    hf_score = float(data.get("hedgeFundsScore") or data.get("hedge_fund_score") or 0)
    hf_trend = "Bullish" if hf_score > 0.5 else "Bearish" if hf_score < 0.3 else "Neutral"

    # Insider Score (0-1 Skala)
    insider_score = float(data.get("insiderScore") or data.get("insider_score") or 0)
    insider_trend = "Positive" if insider_score > 0.5 else "Negative" if insider_score < 0.3 else "Neutral"

    # News Sentiment (0-1 Skala, wobei >0.5 = positiv)
    news_sentiment = float(data.get("newsSentiment") or data.get("news_sentiment") or 0)

    return TipRanksData(
        smart_score=smart_score,
        analyst_consensus=best_consensus or consensus_str,
        analyst_count=analyst_count,
        buy_count=buy,
        hold_count=hold,
        sell_count=sell,
        price_target_avg=pt_avg,
        price_target_high=0.0,  # Nicht im get_assets_data Endpoint
        price_target_low=0.0,
        upside_potential=round(upside, 1),
        hedge_fund_trend=hf_trend,
        hedge_fund_sentiment=hf_score,
        insider_trend=insider_trend,
        news_sentiment=news_sentiment,
        bull_points=[],   # Nicht im get_assets_data — käme über get_bull_bear_summary
        bear_points=[],
        risk_warnings=[],
        investor_sentiment=0.0,
        peers_comparison=[],
    )


def flush_cache():
    """Schreibt den TipRanks-Cache auf Disk."""
    _cache.flush()


def clear_cache():
    """Löscht den TipRanks-Cache."""
    _cache.clear()


def reset_session():
    """Setzt die MCP-Session zurück (z.B. nach Fehler)."""
    global _session_id
    _session_id = None
    logger.info("TipRanks MCP Session zurückgesetzt")




def flush_cache():
    """Schreibt den TipRanks-Cache auf Disk."""
    _cache.flush()


def clear_cache():
    """Löscht den TipRanks-Cache."""
    _cache.clear()


def reset_session():
    """Setzt die MCP-Session zurück (z.B. nach Fehler)."""
    global _session_id
    _session_id = None
    logger.info("TipRanks MCP Session zurückgesetzt")
