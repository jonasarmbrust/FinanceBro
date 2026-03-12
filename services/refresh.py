"""FinanzBro - Daten-Refresh Services.

Enthält die gesamte Refresh-Logik:
- _refresh_data() / _do_refresh(): Voller Refresh aller Quellen
- _quick_price_refresh(): Schneller Kurs-Update (Finnhub + yfinance)
- _update_parqet(): Leichtgewichtiges Parqet-Update
"""
import asyncio
import logging
from datetime import datetime

from state import portfolio_data, refresh_lock, refresh_progress, YFINANCE_ALIASES, TZ_BERLIN
from config import settings
from cache_manager import CacheManager
from models import PortfolioSummary, StockFullData, DataSourceStatus

from fetchers.parqet import fetch_portfolio
from fetchers.fmp import (
    fetch_all_fmp_data, discover_tech_stocks,
)
from fetchers.technical import fetch_technical_indicators
from fetchers.demo_data import (
    get_demo_positions, get_demo_fundamentals,
    get_demo_analyst_data, get_demo_tech_picks,
    get_demo_fmp_ratings,
    get_demo_yfinance_data, get_demo_fear_greed,
)
from fetchers.yfinance_data import fetch_yfinance_data, quick_price_update
from fetchers.fear_greed import fetch_fear_greed_index
from fetchers.currency import fetch_eur_usd_rate, fetch_eur_dkk_rate
from services.currency_converter import CurrencyConverter
from engine.scorer import calculate_score
from engine.rebalancer import calculate_rebalancing
from engine.history import save_snapshot
from engine.analysis import build_analysis_report

logger = logging.getLogger(__name__)


async def _refresh_data():
    """Aktualisiert alle Portfolio-Daten.

    Integriert Daten aus:
      - Parqet (Portfolio-Positionen)
      - FMP (Fundamentals, Analyst, Rating)
      - Technical Indicators (RSI, SMA, Momentum)
      - yFinance (Insider, ESG, Earnings)
      - Fear&Greed Index (Markt-Sentiment)
    """
    if not refresh_lock.locked():
        async with refresh_lock:
            await _do_refresh()
    else:
        logger.info("Refresh bereits aktiv - überspringe")


def _set_progress(step: str, percent: int):
    """Aktualisiert den Refresh-Fortschritt."""
    refresh_progress["step"] = step
    refresh_progress["percent"] = percent


async def _do_refresh():
    """Interne Refresh-Logik (aufgerufen innerhalb des Locks)."""
    portfolio_data["refreshing"] = True
    refresh_progress["started_at"] = datetime.now(tz=TZ_BERLIN).isoformat()
    _set_progress("Starte Refresh...", 0)
    logger.info("🔄 Starte Daten-Refresh...")

    # C4: Error-Aggregation pro Refresh-Zyklus
    _refresh_errors: dict[str, list[str]] = {
        "fmp": [], "yfinance": [], "technical": [],
        "parqet": [], "other": [],
    }

    try:
        # Datenquellen laden
        fear_greed_data = None
        try:
            fear_greed_data = await fetch_fear_greed_index()
            logger.info(f"Fear&Greed: {fear_greed_data.value} ({fear_greed_data.label})")
        except Exception as e:
            logger.warning(f"Fear&Greed nicht verfügbar: {e}")

        # Wechselkurse zentral laden
        _set_progress("Lade Wechselkurse...", 5)
        converter = await CurrencyConverter.create()
        eur_usd_rate = converter.rates.eur_usd

        # --- 1. Lade Portfolio (bevorzugt aus bestehendem Parqet-Update) ---
        _set_progress("Lade Portfolio...", 10)
        existing_summary = portfolio_data.get("summary")
        if existing_summary and existing_summary.stocks:
            # Positionen aus dem letzten Parqet-Update wiederverwenden (spart API-Calls)
            positions = [s.position for s in existing_summary.stocks]
            logger.info(f"📊 Verwende {len(positions)} bestehende Positionen (bereits geladen)")
        else:
            positions = await fetch_portfolio()

        is_demo = False
        if not positions:
            if settings.ENVIRONMENT == "production":
                # Production: NIEMALS Demo-Daten laden!
                # Stattdessen existierende Daten behalten oder leeres Portfolio
                logger.warning(
                    "⚠️ Production: Kein Portfolio von Parqet erhalten. "
                    "Bitte /api/parqet/authorize aufrufen fuer OAuth2-Login."
                )
                return
            else:
                logger.info("📋 Kein Portfolio gefunden - lade Demo-Daten (Entwicklungsmodus)")
                positions = get_demo_positions()
                is_demo = True

        # --- 2. Hole Daten für jede Position ---
        _set_progress(f"Analysiere {len(positions)} Positionen...", 20)
        stocks = []
        scores_dict = {}

        if is_demo:
            demo_fund = get_demo_fundamentals()
            demo_analyst = get_demo_analyst_data()
            demo_fmp = get_demo_fmp_ratings()
            demo_yf = get_demo_yfinance_data()
            if not fear_greed_data:
                fear_greed_data = get_demo_fear_greed()

            for pos in positions:
                fund = demo_fund.get(pos.ticker)
                analyst = demo_analyst.get(pos.ticker)
                fmp_rat = demo_fmp.get(pos.ticker)
                yf = demo_yf.get(pos.ticker)

                score = calculate_score(
                    ticker=pos.ticker,
                    name=pos.name,
                    fundamentals=fund,
                    analyst=analyst,
                    current_price=pos.current_price,
                    fmp_rating=fmp_rat,
                    yfinance_data=yf,
                    fear_greed=fear_greed_data,
                )

                stocks.append(StockFullData(
                    position=pos,
                    fundamentals=fund,
                    analyst=analyst,
                    fmp_rating=fmp_rat,
                    yfinance=yf,
                    score=score,
                ))
                scores_dict[pos.ticker] = score
        else:
            # C1: Daten parallel laden via data_loader Modul
            from services.data_loader import load_positions_batched
            stocks = await load_positions_batched(positions, fear_greed_data)

            # Collect scores
            scores_dict = {s.position.ticker: s.score for s in stocks if s.score}

        # --- 3. Rebalancing ---
        _set_progress("Berechne Rebalancing...", 60)
        rebalancing = calculate_rebalancing(positions, scores_dict, stocks=stocks)

        # --- 4. Tech Picks (nur laden wenn kein Cache vorhanden — spart ~16 FMP-Calls) ---
        if is_demo:
            tech_picks = get_demo_tech_picks()
        elif portfolio_data.get("tech_picks"):
            tech_picks = portfolio_data["tech_picks"]
            logger.info(f"📡 Tech Picks aus Cache: {len(tech_picks)} Empfehlungen")
        else:
            try:
                tech_picks = await discover_tech_stocks(limit=8)
                # AI-Analyse hinzufügen (optional, wenn Gemini konfiguriert)
                if settings.gemini_configured and tech_picks:
                    try:
                        from services.tech_radar_ai import enrich_with_ai_analysis
                        tech_picks = await enrich_with_ai_analysis(tech_picks)
                    except Exception as e:
                        logger.warning(f"Tech-Radar AI-Analyse fehlgeschlagen: {e}")
            except Exception as e:
                logger.error(f"Tech Picks Fehler: {e}")
                tech_picks = get_demo_tech_picks()

        # --- 5. Daily Changes + Preisanpassungen ---
        _set_progress("Lade Tagesänderungen...", 75)
        # Hole Daily Changes per yfinance Batch-Call
        non_cash_tickers = [s.position.ticker for s in stocks if s.position.ticker != "CASH"]
        yf_tickers_map = {t: YFINANCE_ALIASES.get(t, t) for t in non_cash_tickers}
        yf_tickers_unique = list(set(yf_tickers_map.values()))
        daily_changes = {}
        try:
            _, daily_raw = await quick_price_update(yf_tickers_unique)
            for orig, yf_t in yf_tickers_map.items():
                if yf_t in daily_raw:
                    daily_changes[orig] = daily_raw[yf_t]
        except Exception as e:
            logger.debug(f"Daily Changes konnten nicht geladen werden: {e}")

        # Setze daily_change_pct + konvertiere alle Preise nach EUR
        for s in stocks:
            pos = s.position
            if pos.ticker == "CASH":
                pos.price_currency = "EUR"
                continue

            # Daily change setzen
            if pos.ticker in daily_changes:
                pos.daily_change_pct = daily_changes[pos.ticker]

            # Wenn Preis bereits in EUR ist (z.B. von vorherigem Parqet-Update),
            # KEINE erneute Konvertierung durchführen (verhindert Doppelkonvertierung)
            if pos.price_currency == "EUR":
                continue

            # Zentrale Währungskonvertierung
            pos.current_price = converter.to_eur(pos.current_price, pos.ticker)
            pos.price_currency = "EUR"

        # --- 6. Build Summary (alle Werte jetzt in EUR) ---
        _set_progress("Erstelle Zusammenfassung...", 85)
        total_value = sum(s.position.current_value for s in stocks)
        total_cost = sum(s.position.total_cost for s in stocks)
        total_pnl = total_value - total_cost
        total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0

        # Berechne tägliche Gesamtveränderung
        daily_total_eur = 0.0
        for s in stocks:
            pct = s.position.daily_change_pct
            if pct is not None and s.position.ticker != "CASH":
                # daily EUR change = current_value * pct / (100 + pct)
                daily_total_eur += s.position.current_value * pct / (100 + pct)
        daily_total_pct = (daily_total_eur / (total_value - daily_total_eur) * 100) if (total_value - daily_total_eur) > 0 else 0

        summary = PortfolioSummary(
            total_value=round(total_value, 2),
            total_cost=round(total_cost, 2),
            total_pnl=round(total_pnl, 2),
            total_pnl_percent=round(total_pnl_pct, 1),
            num_positions=len(stocks),
            stocks=stocks,
            scores=[s.score for s in stocks if s.score],
            rebalancing=rebalancing,
            tech_picks=tech_picks,
            fear_greed=fear_greed_data,
            is_demo=is_demo,
            eur_usd_rate=eur_usd_rate,
            daily_total_change=round(daily_total_eur, 2),
            daily_total_change_pct=round(daily_total_pct, 2),
        )

        portfolio_data["summary"] = summary
        portfolio_data["last_refresh"] = datetime.now(tz=TZ_BERLIN)

        # Activities cachen (für Attribution, Earnings, Portfolio-History)
        try:
            from fetchers.parqet import fetch_portfolio_activities_raw
            portfolio_data["activities"] = await fetch_portfolio_activities_raw()
        except Exception:
            pass

        # Save daily portfolio snapshot
        try:
            save_snapshot(
                total_value=total_value,
                total_cost=total_cost,
                total_pnl=total_pnl,
                num_positions=len(stocks),
                eur_usd_rate=eur_usd_rate,
            )
        except Exception as e:
            logger.warning(f"Snapshot-Speicherung fehlgeschlagen: {e}")

        _set_progress("Erstelle Analyse-Report...", 90)
        logger.info(f"✅ Refresh abgeschlossen: {len(stocks)} Positionen, Wert: €{total_value:,.2f}")

        # Analyse-Report generieren
        try:
            report = build_analysis_report(
                stocks_with_scores=stocks,
                analysis_level="full",
                total_portfolio_value=total_value,
            )
            portfolio_data["last_analysis"] = report
            logger.info(f"📊 Analyse-Report: Portfolio-Score {report.portfolio_score:.1f} ({report.portfolio_rating.value.upper()})")

            # AI Score-Kommentare generieren (Gemini 2.0 Flash)
            if settings.gemini_configured:
                try:
                    from services.score_commentary import generate_score_commentaries
                    commentaries = await generate_score_commentaries(stocks)
                    for stock in stocks:
                        if stock.score and stock.position.ticker in commentaries:
                            stock.score.ai_comment = commentaries[stock.position.ticker]
                    if commentaries:
                        logger.info(f"🤖 AI-Kommentare: {len(commentaries)} Aktien kommentiert")
                except Exception as e:
                    logger.warning(f"Score-Kommentare fehlgeschlagen: {e}")

            # AI Agent Telegram-Report nach erfolgreicher Analyse senden
            if settings.telegram_configured:
                try:
                    from services.ai_agent import run_daily_report
                    await run_daily_report()
                except Exception as e:
                    logger.warning(f"AI Agent Report fehlgeschlagen: {e}")
        except Exception as e:
            logger.warning(f"Analyse-Report Generierung fehlgeschlagen: {e}")

        # Vertex AI Context Cache aktualisieren (spart Token-Kosten)
        if settings.gemini_configured:
            try:
                from services.vertex_ai import cache_portfolio_context
                await cache_portfolio_context(summary)
            except Exception as e:
                logger.debug(f"Context Caching übersprungen: {e}")

    except Exception as e:
        logger.error(f"❌ Refresh fehlgeschlagen: {e}")
        import traceback
        traceback.print_exc()
        _refresh_errors["other"].append(str(e))
    finally:
        portfolio_data["refreshing"] = False
        _set_progress("Fertig", 100)
        # C4: Error-Summary loggen
        total_errors = sum(len(v) for v in _refresh_errors.values())
        if total_errors > 0:
            error_summary = {k: len(v) for k, v in _refresh_errors.items() if v}
            logger.warning(f"⚠️ Refresh-Fehler: {total_errors} gesamt — {error_summary}")
            for source, errors in _refresh_errors.items():
                for err in errors[:3]:  # Max 3 Fehler pro Quelle loggen
                    logger.debug(f"  [{source}] {err}")
        else:
            logger.info("✅ Refresh fehlerfrei abgeschlossen")
        portfolio_data["refresh_errors"] = {
            k: len(v) for k, v in _refresh_errors.items() if v
        }


async def _quick_price_refresh():
    """Schneller Kurs-Update: Finnhub (Echtzeit) + yfinance (Fallback)."""
    summary = portfolio_data.get("summary")
    if not summary or not summary.stocks:
        return

    if portfolio_data["refreshing"]:
        logger.debug("Voller Refresh aktiv - überspringe Kurs-Update")
        return

    try:
        tickers = [s.position.ticker for s in summary.stocks]
        prices = {}

        # 1. Finnhub Echtzeit-Preise (US-Ticker)
        finnhub_count = 0
        try:
            from fetchers.finnhub_ws import get_streamer
            streamer = get_streamer()
            if streamer.is_connected:
                fh_prices = streamer.get_all_prices()
                for t in tickers:
                    p = fh_prices.get(t.upper())
                    if p and p > 0:
                        prices[t] = p
        except Exception as e:
            logger.debug(f"Finnhub-Preise nicht verfügbar: {e}")

        finnhub_count = len(prices)  # Alle bisherigen sind von Finnhub

        # 2. yfinance Fallback für restliche Ticker (über Aliases)
        remaining = [t for t in tickers if t not in prices and t != "CASH"]
        if remaining:
            # Map durch Aliases (z.B. DTEGY → DTE.DE) damit yfinance
            # den richtigen Börsenplatz abfragt
            ticker_to_yf = {t: YFINANCE_ALIASES.get(t, t) for t in remaining}
            yf_tickers = list(set(ticker_to_yf.values()))
            yf_prices, _ = await quick_price_update(yf_tickers)
            # Map zurück auf Original-Ticker
            for orig, yf_t in ticker_to_yf.items():
                if yf_t in yf_prices:
                    prices[orig] = yf_prices[yf_t]

        if not prices:
            return

        updated = 0
        # Zentrale Währungskonvertierung
        converter = await CurrencyConverter.create(
            eur_usd_override=summary.eur_usd_rate if summary.eur_usd_rate > 0 else None
        )

        total_value = 0.0
        total_cost = 0.0

        for stock in summary.stocks:
            ticker = stock.position.ticker
            if ticker == "CASH":
                # Cash-Position nicht aktualisieren
                total_value += stock.position.current_value
                total_cost += stock.position.total_cost
                continue

            if ticker in prices:
                raw_price = prices[ticker]
                stock.position.current_price = converter.to_eur(raw_price, ticker)
                stock.position.price_currency = "EUR"
                updated += 1

            total_value += stock.position.current_value
            total_cost += stock.position.total_cost

        # Update summary totals
        summary.total_value = round(total_value, 2)
        summary.total_cost = round(total_cost, 2)
        total_pnl = total_value - total_cost
        summary.total_pnl = round(total_pnl, 2)
        summary.total_pnl_percent = round((total_pnl / total_cost * 100) if total_cost > 0 else 0, 1)
        summary.last_updated = datetime.now(tz=TZ_BERLIN)

        yf_count = updated - finnhub_count
        logger.info(
            f"⚡ Quick-Update: {updated}/{len(tickers)} Kurse aktualisiert "
            f"(Finnhub: {finnhub_count}, yfinance: {yf_count}), "
            f"Wert: €{total_value:,.2f}"
        )

        # Save snapshot
        try:
            save_snapshot(
                total_value=total_value,
                total_cost=total_cost,
                total_pnl=total_pnl,
                num_positions=len(summary.stocks),
                eur_usd_rate=summary.eur_usd_rate,
            )
        except Exception:
            pass

    except Exception as e:
        logger.warning(f"Quick-Price-Update fehlgeschlagen: {e}")


async def _update_parqet():
    """Delegiert an services.portfolio_builder (C1 Refactoring)."""
    from services.portfolio_builder import update_parqet
    return await update_parqet()
