"""FinanceBro - TipRanks MCP Fetcher

Kommuniziert mit dem TipRanks MCP-Server (https://mcp.tipranks.com/mcp/)
über das MCP-Protokoll (JSON-RPC über HTTP, Streamable HTTP Transport).

Features:
  - MCP Session-Management (initialize → tools/call)
  - Rate Limiting (pro Minute + pro Tag)
  - CacheManager-Integration (6h TTL)
  - Graceful Degradation bei Fehlern

Authentifizierung via API-Key als Query-Parameter.
"""
import asyncio
import json
import logging
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


async def _initialize_session(client: httpx.AsyncClient) -> Optional[str]:
    """Initialisiert eine MCP-Session und gibt die Session-ID zurück.

    Sendet einen JSON-RPC `initialize` Request an den MCP-Server.
    Die Session-ID wird aus dem Response-Header `Mcp-Session-Id` extrahiert.
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
            headers={"Content-Type": "application/json"},
            timeout=15.0,
        )
        resp.raise_for_status()

        session_id = resp.headers.get("Mcp-Session-Id") or resp.headers.get("mcp-session-id")
        if session_id:
            logger.info(f"TipRanks MCP Session initialisiert: {session_id[:12]}...")
            return session_id

        # Fallback: Manche MCP-Server liefern Session-ID im Body
        body = resp.json()
        if "error" in body:
            logger.error(f"TipRanks MCP initialize Fehler: {body['error']}")
            return None

        logger.warning("TipRanks MCP: Keine Session-ID im Response-Header")
        return None

    except httpx.HTTPStatusError as e:
        logger.error(f"TipRanks MCP initialize HTTP-Fehler: {e.response.status_code}")
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

    headers = {
        "Content-Type": "application/json",
        "Mcp-Session-Id": session_id,
    }

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
        body = resp.json()

        if "error" in body:
            logger.error(f"TipRanks MCP Tool-Fehler ({tool_name}): {body['error']}")
            return None

        # Ergebnis extrahieren: result.content[0].text → JSON-String
        result = body.get("result", {})
        content = result.get("content", [])
        if content and isinstance(content, list) and len(content) > 0:
            text_data = content[0].get("text", "")
            if text_data:
                return json.loads(text_data)

        logger.warning(f"TipRanks MCP: Leeres Ergebnis für {tool_name}")
        return None

    except httpx.HTTPStatusError as e:
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

    Unterstützt verschiedene Response-Formate (Einzel-Ticker und Batch).
    """
    from models import TipRanksData

    # Response kann direkt die Daten enthalten oder unter dem Ticker-Key
    data = raw
    if ticker in raw:
        data = raw[ticker]
    elif "data" in raw:
        data = raw["data"]
        if isinstance(data, dict) and ticker in data:
            data = data[ticker]
        elif isinstance(data, list) and len(data) > 0:
            # Erstes Element nehmen (bei Einzel-Ticker-Request)
            data = data[0]

    if not data or not isinstance(data, dict):
        return None

    # Smart Score extrahieren (Pflichtfeld)
    smart_score = (
        data.get("tipranksSmartScore")
        or data.get("smartScore")
        or data.get("smart_score")
    )
    if smart_score is None:
        logger.debug(f"TipRanks {ticker}: Kein Smart Score in Response")
        return None

    smart_score = max(1, min(10, int(smart_score)))

    # Analyst-Daten
    analyst_consensus_data = data.get("analystConsensus") or data.get("analyst_consensus") or {}
    if isinstance(analyst_consensus_data, str):
        consensus_str = analyst_consensus_data
        buy = hold = sell = analyst_count = 0
    else:
        consensus_str = analyst_consensus_data.get("consensus", "Hold")
        buy = int(analyst_consensus_data.get("buy", 0) or 0)
        hold = int(analyst_consensus_data.get("hold", 0) or 0)
        sell = int(analyst_consensus_data.get("sell", 0) or 0)
        analyst_count = buy + hold + sell

    # Preisziele
    price_targets = data.get("priceTarget") or data.get("price_target") or {}
    if isinstance(price_targets, dict):
        pt_avg = float(price_targets.get("average", 0) or 0)
        pt_high = float(price_targets.get("high", 0) or 0)
        pt_low = float(price_targets.get("low", 0) or 0)
    else:
        pt_avg = pt_high = pt_low = 0.0

    # Upside berechnen
    upside = float(data.get("upsidePotential", 0) or data.get("upside_potential", 0) or 0)

    # Hedge Fund Daten
    hf_data = data.get("hedgeFundActivity") or data.get("hedge_fund") or {}
    if isinstance(hf_data, dict):
        hf_trend = hf_data.get("trend", "")
        hf_sentiment = float(hf_data.get("sentiment", 0.0) or 0)
    else:
        hf_trend = ""
        hf_sentiment = 0.0

    # Insider-Trend
    insider_data = data.get("insiderActivity") or data.get("insider") or {}
    if isinstance(insider_data, dict):
        insider_trend = insider_data.get("trend", "")
    elif isinstance(insider_data, str):
        insider_trend = insider_data
    else:
        insider_trend = ""

    # News Sentiment
    news_sentiment = float(data.get("newsSentiment", 0.0) or data.get("news_sentiment", 0.0) or 0)

    # Investor Sentiment
    investor_sentiment = float(
        data.get("investorSentiment", 0.0) or data.get("investor_sentiment", 0.0) or 0
    )

    # Bull/Bear-Punkte und Risiko-Warnungen
    bull_points = data.get("bullPoints") or data.get("bull_points") or []
    bear_points = data.get("bearPoints") or data.get("bear_points") or []
    risk_warnings = data.get("riskWarnings") or data.get("risk_warnings") or []

    # Peers Comparison
    peers = data.get("peersComparison") or data.get("peers_comparison") or []

    return TipRanksData(
        smart_score=smart_score,
        analyst_consensus=consensus_str,
        analyst_count=analyst_count,
        buy_count=buy,
        hold_count=hold,
        sell_count=sell,
        price_target_avg=pt_avg,
        price_target_high=pt_high,
        price_target_low=pt_low,
        upside_potential=upside,
        hedge_fund_trend=hf_trend,
        hedge_fund_sentiment=hf_sentiment,
        insider_trend=insider_trend,
        news_sentiment=news_sentiment,
        bull_points=bull_points if isinstance(bull_points, list) else [],
        bear_points=bear_points if isinstance(bear_points, list) else [],
        risk_warnings=risk_warnings if isinstance(risk_warnings, list) else [],
        investor_sentiment=investor_sentiment,
        peers_comparison=peers if isinstance(peers, list) else [],
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
