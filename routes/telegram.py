"""FinanzBro - Telegram Webhook Route.

Empfängt eingehende Nachrichten von Telegram via Webhook
und leitet sie an den Command Handler weiter.

Webhook ist über ein Secret-Token in der URL geschützt:
  /api/telegram/webhook/<secret>
"""
import secrets
import logging

from fastapi import APIRouter, Request, Response

from config import settings

router = APIRouter(tags=["telegram"])

logger = logging.getLogger(__name__)


@router.post("/api/telegram/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request):
    """Empfängt Telegram-Updates via Webhook.

    Das Secret in der URL muss mit TELEGRAM_WEBHOOK_SECRET übereinstimmen.
    """
    # Secret-Token prüfen
    if not settings.TELEGRAM_WEBHOOK_SECRET or \
       not secrets.compare_digest(secret, settings.TELEGRAM_WEBHOOK_SECRET):
        logger.warning("Telegram-Webhook: Ungültiges Secret")
        return Response(status_code=403)

    try:
        update = await request.json()
        logger.debug(f"Telegram-Update empfangen: {update.get('update_id', '?')}")

        from services.telegram_bot import handle_update
        import asyncio
        asyncio.create_task(handle_update(update))

        return Response(status_code=200)

    except Exception as e:
        logger.error(f"Telegram-Webhook-Fehler: {e}")
        return Response(status_code=200)
