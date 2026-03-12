"""FinanzBro - FastAPI Backend

Hauptserver: App-Erstellung, Lifespan-Management und Router-Einbindung.
Die gesamte Geschäftslogik lebt in services/ und routes/.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from config import settings
from cache_manager import CacheManager
from state import portfolio_data

from services.refresh import _refresh_data, _quick_price_refresh, _update_parqet
from routes.portfolio import router as portfolio_router
from routes.refresh import router as refresh_router
from routes.streaming import router as streaming_router
from routes.analysis import router as analysis_router
from routes.analytics import router as analytics_router
from routes.telegram import router as telegram_router
from routes.parqet_oauth import router as parqet_oauth_router

logger = logging.getLogger(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """App startup/shutdown."""
    logger.info("\U0001f680 FinanzBro startet...")
    logger.info(f"   Environment: {settings.ENVIRONMENT}")
    logger.info(f"   Port: {settings.SERVER_PORT}")
    logger.info(f"   Demo-Mode: {settings.demo_mode}")
    logger.info(f"   Finnhub: {'✅ API-Key vorhanden' if settings.FINNHUB_API_KEY else '❌ Kein API-Key'}")

    # Volatile Caches beim Start löschen (FMP, Stocknear, yFinance, etc.)
    # Parqet-Positionen und Wechselkurse bleiben erhalten
    CacheManager.clear_volatile_caches()

    # Fast startup: Parqet API + yFinance prices only (no heavy FMP/Stocknear/AV)
    asyncio.create_task(_update_parqet())

    # Start Finnhub WebSocket (if API key configured)
    finnhub_streamer = None
    try:
        from fetchers.finnhub_ws import get_streamer
        finnhub_streamer = get_streamer()
        await finnhub_streamer.start()
    except Exception as e:
        logger.warning(f"Finnhub-Start fehlgeschlagen: {e}")

    # Subscribe portfolio tickers to Finnhub after Parqet loads
    async def _subscribe_finnhub():
        """Warte auf Portfolio-Daten, dann Ticker bei Finnhub abonnieren."""
        await asyncio.sleep(15)  # Warte bis Parqet geladen ist
        summary = portfolio_data.get("summary")
        if summary and summary.stocks and finnhub_streamer:
            tickers = [s.position.ticker for s in summary.stocks]
            finnhub_streamer.subscribe(tickers)

    if finnhub_streamer and settings.FINNHUB_API_KEY:
        asyncio.create_task(_subscribe_finnhub())

    # Schedule: Einzige geplante Analyse um 16:15 CET
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()

        scheduler.add_job(
            _refresh_data, "cron",
            hour=16, minute=15,
            id="daily_analysis",
        )
        logger.info("\U0001f4ca Vollständige Analyse geplant um 16:15 CET")

        # Weekly Digest (Sonntag 18:00 CET)
        async def _run_weekly_digest():
            try:
                from services.weekly_digest import send_weekly_digest
                await send_weekly_digest()
            except Exception as e:
                logger.warning(f"Weekly Digest fehlgeschlagen: {e}")

        scheduler.add_job(
            _run_weekly_digest, "cron",
            day_of_week="sun", hour=18, minute=0,
            id="weekly_digest",
        )
        logger.info("📧 Wöchentlicher Digest geplant: Sonntag 18:00 CET")

        # AI Finance Agent wird automatisch nach jeder Analyse in _do_refresh() getriggert
        if settings.telegram_configured:
            logger.info("🤖 AI Finance Agent: Wird nach Analyse automatisch getriggert (Telegram-Report)")
        else:
            logger.info("🤖 AI Finance Agent übersprungen (Telegram nicht konfiguriert)")

        # Telegram Webhook registrieren (wenn auf Cloud Run)
        if settings.telegram_configured and settings.ENVIRONMENT == "production":
            async def _register_webhook():
                """Registriert den Telegram-Webhook bei App-Start."""
                await asyncio.sleep(5)  # Warte bis Server ready
                try:
                    import httpx
                    # Cloud Run URL aus Umgebungsvariable (automatisch gesetzt)
                    import os
                    service_url = os.getenv("CLOUD_RUN_URL", "").rstrip("/")
                    if not service_url:
                        # Fallback: K_SERVICE ist Cloud Run Env-Var
                        k_service = os.getenv("K_SERVICE", "")
                        k_region = os.getenv("CLOUD_RUN_REGION", "europe-west1")
                        project = os.getenv("GOOGLE_CLOUD_PROJECT", "")
                        if k_service:
                            service_url = f"https://{k_service}-{project}.{k_region}.run.app"
                    
                    if service_url:
                        webhook_url = f"{service_url}/api/telegram/webhook"
                        api_url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/setWebhook"
                        async with httpx.AsyncClient(timeout=10) as client:
                            r = await client.post(api_url, json={"url": webhook_url})
                            if r.status_code == 200 and r.json().get("ok"):
                                logger.info(f"🔗 Telegram-Webhook registriert: {webhook_url}")
                            else:
                                logger.warning(f"Telegram-Webhook fehlgeschlagen: {r.text}")
                    else:
                        logger.info("🔗 Telegram-Webhook: Keine Cloud Run URL — lokal Polling nutzen")
                except Exception as e:
                    logger.warning(f"Telegram-Webhook-Registrierung fehlgeschlagen: {e}")
            asyncio.create_task(_register_webhook())

        # Intraday Kurs-Updates (alle 15min während Marktzeiten, 0 FMP-Calls)
        async def _intraday_price_update():
            """Aktualisiert Kurse via yfinance batch (kein FMP-Verbrauch)."""
            from state import portfolio_data
            summary = portfolio_data.get("summary")
            if not summary or not summary.stocks:
                return
            tickers = [s.position.ticker for s in summary.stocks if s.position.ticker != "CASH"]
            if not tickers:
                return
            try:
                from fetchers.yfinance_data import quick_price_update
                from state import YFINANCE_ALIASES
                yf_map = {t: YFINANCE_ALIASES.get(t, t) for t in tickers}
                prices, daily_changes = await quick_price_update(list(set(yf_map.values())))
                updated = 0
                for stock in summary.stocks:
                    t = stock.position.ticker
                    yf_t = yf_map.get(t, t)
                    if yf_t in prices and prices[yf_t] > 0:
                        stock.position.current_price = prices[yf_t]
                        updated += 1
                    if yf_t in daily_changes:
                        stock.position.daily_change_pct = daily_changes[yf_t]
                if updated:
                    logger.info(f"📈 Intraday-Update: {updated}/{len(tickers)} Kurse aktualisiert")
            except Exception as e:
                logger.debug(f"Intraday-Update fehlgeschlagen: {e}")

        scheduler.add_job(
            _intraday_price_update, "interval",
            minutes=settings.PRICE_UPDATE_INTERVAL_MIN,
            id="intraday_prices",
            hour="8-22",  # Nur während Marktzeiten (CET)
            day_of_week="mon-fri",  # Nur Werktage (DA3)
        )
        logger.info(f"📈 Intraday Kurs-Updates alle {settings.PRICE_UPDATE_INTERVAL_MIN}min (Mo-Fr 08-22 Uhr)")

        scheduler.start()
    except Exception as e:
        logger.warning(f"Scheduler konnte nicht gestartet werden: {e}")

    yield

    # Shutdown: Finnhub WebSocket sauber schließen
    if finnhub_streamer:
        await finnhub_streamer.stop()
    logger.info("FinanzBro beendet.")


# Create FastAPI app
app = FastAPI(
    title="FinanzBro",
    description="Aktienportfolio Dashboard & Advisor",
    version="1.0.0",
    lifespan=lifespan,
)

# GZip-Kompression für alle Responses (>500 Bytes)
# → ~70% Payload-Reduktion für JSON-APIs und Static Files
app.add_middleware(GZipMiddleware, minimum_size=500)

# Static files mit Cache-Control Headers (1 Stunde)
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount(
    "/static",
    StaticFiles(directory=str(STATIC_DIR)),
    name="static",
)

# Include routers
app.include_router(portfolio_router)
app.include_router(refresh_router)
app.include_router(streaming_router)
app.include_router(analysis_router)
app.include_router(analytics_router)
app.include_router(telegram_router)
app.include_router(parqet_oauth_router)


if __name__ == "__main__":
    import uvicorn
    is_dev = settings.ENVIRONMENT == "development"

    uvicorn.run(
        "main:app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        reload=is_dev,
        # Cache-Verzeichnis vom File-Watcher ausschließen
        # → verhindert Endlos-Neustarts durch Cache-Dateiänderungen
        reload_excludes=["cache/*", "*.json"] if is_dev else None,
    )
