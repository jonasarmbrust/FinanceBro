"""FinanceBro - Parqet Token Management

Verwaltet Parqet API Authentication:
- JWT Token-Validierung (Expiration-Check)
- Token-Renewal-Kette: SQLite → Datei → Env → Firefox-Cookie → OAuth2 Refresh
- Token-Persistierung in SQLite (via Litestream nach GCS repliziert)
- asyncio.Lock verhindert parallele Refreshes (Token-Rotation-Schutz)
"""
import asyncio
import base64
import glob
import json
import logging
import os
import shutil
import sqlite3
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)

# Deduplizierung: Telegram-Alert nur 1x pro Tag senden
_token_alert_sent_date: str | None = None

# Verhindert parallele Token-Refreshes (Parqet rotiert den Refresh-Token
# bei jedem Request — parallele Refreshes erzeugen mehrere rotierende Tokens,
# von denen nur einer gueltig ist)
_token_refresh_lock = asyncio.Lock()

TOKEN_FILE = settings.CACHE_DIR / "parqet_tokens.json"

# Parqet API URLs
PARQET_TOKEN_URL = f"{settings.PARQET_API_BASE_URL}/oauth2/token"


def is_token_expired(token: str, margin_seconds: int = 60) -> bool:
    """Prueft ob ein JWT-Token abgelaufen ist.

    Dekodiert den JWT-Payload (ohne Signaturpruefung) und vergleicht
    das 'exp'-Feld mit der aktuellen Zeit.

    Args:
        token: Der JWT-Token-String
        margin_seconds: Sicherheitsmarge (Default: 60s vor Ablauf = abgelaufen)

    Returns:
        True wenn abgelaufen oder nicht parsbar, False wenn gueltig
    """
    try:
        # JWT hat 3 Teile: header.payload.signature
        parts = token.split(".")
        if len(parts) != 3:
            return True  # Kein gueltiger JWT

        # Payload dekodieren (Base64URL)
        payload_b64 = parts[1]
        # Base64URL padding auffuellen
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding

        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        payload = json.loads(payload_bytes)

        exp = payload.get("exp")
        if exp is None:
            return False  # Kein Ablaufdatum = nicht ablaufend

        now = time.time()
        is_expired = now >= (exp - margin_seconds)

        if is_expired:
            exp_dt = datetime.fromtimestamp(exp)
            logger.debug(f"Parqet Token abgelaufen seit {exp_dt.strftime('%d.%m.%Y %H:%M')}")

        return is_expired

    except Exception as e:
        logger.debug(f"JWT-Decode fehlgeschlagen: {e}")
        return True  # Im Zweifel als abgelaufen behandeln


def refresh_token_from_firefox() -> str | None:
    """Liest frische Parqet Tokens aus Firefox-Cookies.

    Parqet speichert:
    - 'parqet-access-token': JWT Access Token
    - 'parqet-refresh-token': Supabase Refresh Token (rotiert bei jedem Use!)

    Beide werden zusammen gespeichert, damit Cloud Run den Refresh-Token
    fuer automatische Erneuerung ueber Supabase nutzen kann.
    """
    try:
        appdata = os.environ.get("APPDATA", "")
        profiles = glob.glob(os.path.join(appdata, "Mozilla", "Firefox", "Profiles", "*"))
        for profile_dir in profiles:
            cookies_db = os.path.join(profile_dir, "cookies.sqlite")
            if not os.path.exists(cookies_db):
                continue
            tmp = os.path.join(tempfile.gettempdir(), "parqet_cookie_refresh.sqlite")
            shutil.copy2(cookies_db, tmp)
            try:
                conn = sqlite3.connect(tmp)
                cur = conn.cursor()
                # Access Token
                cur.execute("SELECT value FROM moz_cookies WHERE host LIKE '%parqet%' AND name='parqet-access-token'")
                row = cur.fetchone()
                access_token = row[0] if row else None
                # Refresh Token (Supabase rotiert diesen!)
                cur.execute("SELECT value FROM moz_cookies WHERE host LIKE '%parqet%' AND name='parqet-refresh-token'")
                row = cur.fetchone()
                refresh_token = row[0] if row else ""
                conn.close()

                if access_token:
                    if is_token_expired(access_token):
                        logger.info("Firefox Parqet-Token ist ebenfalls abgelaufen")
                        continue
                    logger.info(f"Parqet Token aus Firefox erneuert (Laenge: {len(access_token)})")
                    # Persistieren — inkl. frischem Refresh-Token!
                    settings.PARQET_ACCESS_TOKEN = access_token
                    save_token_file(access_token, refresh_token or settings.PARQET_REFRESH_TOKEN or "")
                    return access_token
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)
    except Exception as e:
        logger.debug(f"Firefox Token-Refresh fehlgeschlagen: {e}")
    return None


def get_valid_token() -> Optional[str]:
    """Gibt den aktuellen Access-Token zurück.

    Prioritaet: SQLite (Litestream) → Token-Datei → Env-Var.
    SQLite ist die primaere Quelle, da sie via Litestream nach GCS
    repliziert wird und Deployments ueberlebt.
    """
    # 1. SQLite (primaer — ueberlebt Deployments via Litestream)
    stored = load_token_file()
    if stored and stored.get("access_token"):
        return stored["access_token"]

    # 2. Env-Var (Fallback)
    if settings.PARQET_ACCESS_TOKEN:
        return settings.PARQET_ACCESS_TOKEN

    return None




# ---------------------------------------------------------------------------
# Parqet Connect API (OAuth2 PKCE)
# ---------------------------------------------------------------------------

PARQET_CONNECT_AUTH_URL = "https://connect.parqet.com/oauth2/authorize"
PARQET_CONNECT_TOKEN_URL = "https://connect.parqet.com/oauth2/token"
PARQET_CLIENT_ID = "019cdd20-f5b5-7058-9b45-9608c2aeae51"

# PKCE state stored in memory (only needed during initial auth flow)
_pkce_state: dict = {}


def _generate_code_verifier() -> str:
    """Generiert einen zufaelligen PKCE code_verifier (43-128 Zeichen)."""
    import secrets
    return secrets.token_urlsafe(64)[:96]


def _generate_code_challenge(verifier: str) -> str:
    """Berechnet den PKCE code_challenge (S256) aus dem code_verifier."""
    import hashlib
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def generate_oauth_url(redirect_uri: str) -> tuple[str, str]:
    """Generiert die OAuth2-Autorisierungs-URL fuer Parqet Connect.

    Returns:
        Tuple von (authorize_url, code_verifier)
        Der code_verifier muss fuer den Token-Tausch gespeichert werden.
    """
    import secrets
    code_verifier = _generate_code_verifier()
    code_challenge = _generate_code_challenge(code_verifier)
    state = secrets.token_urlsafe(32)

    # State + Verifier speichern fuer den Callback
    _pkce_state["state"] = state
    _pkce_state["code_verifier"] = code_verifier
    _pkce_state["redirect_uri"] = redirect_uri

    params = {
        "client_id": PARQET_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "portfolio:read",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{PARQET_CONNECT_AUTH_URL}?{query}"
    logger.info(f"OAuth2 URL generiert (state={state[:8]}...)")
    return url, code_verifier


async def exchange_code_for_tokens(
    code: str, state: str, redirect_uri: str
) -> Optional[str]:
    """Tauscht den Authorization Code gegen Access + Refresh Token.

    Wird vom Callback-Endpoint aufgerufen.
    """
    # State pruefen
    expected_state = _pkce_state.get("state")
    if state != expected_state:
        logger.error(f"OAuth2: State mismatch (expected={expected_state}, got={state})")
        return None

    code_verifier = _pkce_state.get("code_verifier", "")

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                PARQET_CONNECT_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "client_id": PARQET_CLIENT_ID,
                    "code": code,
                    "code_verifier": code_verifier,
                    "redirect_uri": redirect_uri,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if resp.status_code != 200:
                logger.error(
                    f"OAuth2 Token-Exchange fehlgeschlagen: {resp.status_code} – "
                    f"{resp.text[:300]}"
                )
                return None

            token_data = resp.json()
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token", "")

            if not access_token:
                logger.error("OAuth2: Kein access_token in Antwort")
                return None

            save_token_file(access_token, refresh_token)
            settings.PARQET_ACCESS_TOKEN = access_token
            logger.info("✅ Parqet Connect API: Tokens erhalten und gespeichert")
            return access_token

    except Exception as e:
        logger.error(f"OAuth2 Token-Exchange Fehler: {e}")
        return None


async def refresh_connect_token() -> Optional[str]:
    """Erneuert den Parqet-Token ueber die Connect API (OAuth2 refresh_token).

    Nutzt connect.parqet.com/oauth2/token mit grant_type=refresh_token.
    Funktioniert auf Cloud Run ohne Browser!
    """
    refresh_token = None

    # Token-Datei zuerst pruefen (kann sich zur Laufzeit aendern)
    stored = load_token_file()
    if stored and stored.get("refresh_token"):
        refresh_token = stored["refresh_token"]

    if not refresh_token:
        refresh_token = settings.PARQET_REFRESH_TOKEN

    if not refresh_token:
        logger.warning("Parqet: Kein Refresh-Token vorhanden")
        return None

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                PARQET_CONNECT_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": PARQET_CLIENT_ID,
                    "refresh_token": refresh_token,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if resp.status_code != 200:
                logger.warning(
                    f"Parqet Connect Token-Refresh: {resp.status_code} – "
                    f"{resp.text[:200]}"
                )
                return None

            token_data = resp.json()
            new_access = token_data.get("access_token")
            new_refresh = token_data.get("refresh_token", refresh_token)

            if not new_access:
                logger.error("Parqet Connect Refresh: Kein access_token in Antwort")
                return None

            # Neuen Refresh-Token speichern (Parqet kann ihn rotieren)
            save_token_file(new_access, new_refresh)
            settings.PARQET_ACCESS_TOKEN = new_access
            logger.info("🔄 Parqet Token ueber Connect API erneuert")
            return new_access

    except Exception as e:
        logger.error(f"Parqet Connect Token-Refresh Fehler: {e}")
        return None


async def refresh_oauth_token() -> Optional[str]:
    """Alias fuer refresh_connect_token — wird von parqet.py importiert."""
    return await refresh_connect_token()


async def ensure_valid_token() -> str | None:
    """Stellt sicher, dass ein gueltiger Parqet-Token verfuegbar ist.

    Renewal-Kette:
    1. Gespeicherter Token pruefen (SQLite → Datei → Env)
    2. Parqet Connect API Refresh (funktioniert auf Cloud Run!)
    3. Firefox-Cookie als Fallback (nur lokal)

    WICHTIG: Nutzt asyncio.Lock um parallele Refreshes zu verhindern.
    Parqet rotiert den Refresh-Token bei jedem Use — parallele Refreshes
    erzeugen mehrere Tokens, von denen nur einer gueltig ist.

    Returns:
        Gueltiger Access-Token oder None
    """
    # Schritt 1: Gespeicherten Token pruefen (ohne Lock — nur Lesen)
    token = get_valid_token()
    if token and not is_token_expired(token):
        return token

    # Ab hier: Token muss erneuert werden → Lock verwenden
    async with _token_refresh_lock:
        # Double-Check: Vielleicht hat ein anderer Request schon erneuert
        token = get_valid_token()
        if token and not is_token_expired(token):
            return token

        if token:
            logger.info("Parqet Token abgelaufen, starte automatische Erneuerung...")
        else:
            logger.info("Kein Parqet Token vorhanden, versuche Erneuerung...")

        # Schritt 2: Connect API Refresh-Token (Cloud Run kompatibel!)
        stored = load_token_file()
        if settings.PARQET_REFRESH_TOKEN or (stored and stored.get("refresh_token")):
            logger.info("Versuche Parqet Connect API Token-Refresh...")
            new_token = await refresh_connect_token()
            if new_token and not is_token_expired(new_token):
                logger.info("✅ Parqet Token ueber Connect API erneuert")
                return new_token

        # Schritt 3: Firefox-Cookie (nur lokal)
        new_token = refresh_token_from_firefox()
        if new_token and not is_token_expired(new_token):
            logger.info("Parqet Token aus Firefox erneuert")
            return new_token

        logger.error(
            "Parqet Token-Erneuerung fehlgeschlagen. "
            "Bitte /api/parqet/authorize aufrufen fuer OAuth2-Login."
        )

        # Telegram-Alert senden (max 1x pro Tag)
        await _notify_token_expired()

        return None


async def _notify_token_expired():
    """Sendet einen Telegram-Alert wenn der Parqet-Token abgelaufen ist.

    Max 1x pro Tag, um Alert-Spam zu vermeiden.
    """
    global _token_alert_sent_date

    if not settings.telegram_configured:
        return

    today = datetime.now().strftime("%Y-%m-%d")
    if _token_alert_sent_date == today:
        return  # Bereits heute gesendet

    try:
        from services.telegram import send_message

        cloud_run_url = os.environ.get("CLOUD_RUN_URL", "")
        reauth_link = f"{cloud_run_url}/api/parqet/authorize" if cloud_run_url else "/api/parqet/authorize"

        await send_message(
            "🔴 *FinanceBro: Parqet-Token abgelaufen!*\n\n"
            "Der Parqet Refresh-Token ist ungültig. "
            "Ohne gültige Parqet-Verbindung können keine Portfolio-Daten geladen werden.\n\n"
            "⚠️ *Auswirkung:* Keine Daily Reports, Market Alerts oder News-Kurator-Alerts.\n\n"
            f"🔗 *Jetzt neu autorisieren:*\n{reauth_link}"
        )

        _token_alert_sent_date = today
        logger.info("📨 Telegram-Alert gesendet: Parqet-Token abgelaufen")

    except Exception as e:
        logger.debug(f"Token-Ablauf Telegram-Alert fehlgeschlagen: {e}")


def load_token_file() -> Optional[dict]:
    """Laedt gespeicherte Tokens.

    Prioritaet:
    1. SQLite system_state (via Litestream nach GCS repliziert — ueberlebt Deployments)
    2. Lokale JSON-Datei (Fallback fuer lokale Entwicklung)
    """
    # 1. SQLite (primaere Quelle — deployment-sicher)
    try:
        from database import get_system_state
        access = get_system_state("parqet_access_token", "")
        refresh = get_system_state("parqet_refresh_token", "")
        if access:
            return {
                "access_token": access,
                "refresh_token": refresh,
                "updated_at": get_system_state("parqet_token_updated_at", ""),
            }
    except Exception:
        pass

    # 2. Lokale JSON-Datei (Fallback)
    if TOKEN_FILE.exists():
        try:
            return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def save_token_file(access_token: str, refresh_token: str):
    """Persistiert Tokens in SQLite und als lokale JSON-Datei.

    SQLite wird via Litestream nach GCS repliziert (sync-interval: 5s).
    Damit ueberleben die Tokens Container-Neustarts UND Deployments —
    ohne Cloud Run Env-Vars patchen zu muessen (was 409 Conflicts
    bei gleichzeitigen Deployments verursacht hat).
    """
    now = datetime.now().isoformat()

    # 1. SQLite (primaer — deployment-sicher via Litestream)
    try:
        from database import set_system_state
        set_system_state("parqet_access_token", access_token)
        set_system_state("parqet_refresh_token", refresh_token)
        set_system_state("parqet_token_updated_at", now)
        logger.debug("Parqet Tokens in SQLite gespeichert")
    except Exception as e:
        logger.warning(f"Parqet Token SQLite-Persist fehlgeschlagen: {e}")

    # 2. Lokale JSON-Datei (Fallback + lokale Entwicklung)
    try:
        TOKEN_FILE.write_text(
            json.dumps({
                "access_token": access_token,
                "refresh_token": refresh_token,
                "updated_at": now,
            }, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        logger.debug(f"Token JSON-Datei konnte nicht geschrieben werden: {e}")

