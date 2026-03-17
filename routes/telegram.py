"""FinanzBro - Telegram Webhook Route.

Empfängt eingehende Nachrichten von Telegram via Webhook
und leitet sie an den Command Handler weiter.

Webhook ist über ein Secret-Token in der URL geschützt:
  /api/telegram/webhook/<secret>

Nutzt Starlette BackgroundTasks: Telegram bekommt sofort 200 OK,
aber handle_update läuft im selben Request-Lifecycle weiter.
So bleibt Cloud Run am Leben bis die Verarbeitung fertig ist.
"""
import secrets
import logging

from fastapi import APIRouter, Request, BackgroundTasks
from starlette.responses import Response

from config import settings

router = APIRouter(tags=["telegram"])

logger = logging.getLogger(__name__)


async def _process_update(update: dict):
    """Verarbeitet ein Telegram-Update (Background Task).

    Läuft nach dem HTTP-200-Response, aber innerhalb des
    gleichen Request-Lifecycles — Cloud Run hält die Instance.
    """
    try:
        from services.telegram_bot import handle_update
        await handle_update(update)
    except Exception as e:
        logger.error(f"Telegram-Update-Verarbeitung fehlgeschlagen: {e}", exc_info=True)


@router.post("/api/telegram/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request, background_tasks: BackgroundTasks):
    """Empfängt Telegram-Updates via Webhook.

    Gibt sofort 200 zurück (Telegram-Timeout = 60s).
    Die eigentliche Verarbeitung läuft als BackgroundTask
    im selben Request-Lifecycle weiter.
    """
    # Secret-Token prüfen
    if not settings.TELEGRAM_WEBHOOK_SECRET or \
       not secrets.compare_digest(secret, settings.TELEGRAM_WEBHOOK_SECRET):
        logger.warning("Telegram-Webhook: Ungültiges Secret")
        return Response(status_code=403)

    try:
        update = await request.json()
        logger.info(f"Telegram-Update empfangen: {update.get('update_id', '?')}")

        background_tasks.add_task(_process_update, update)

        return Response(status_code=200)

    except Exception as e:
        logger.error(f"Telegram-Webhook-Fehler: {e}")
        return Response(status_code=200)


