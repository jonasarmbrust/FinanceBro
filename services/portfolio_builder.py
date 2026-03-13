"""FinanzBro - Portfolio Builder (C1 Refactoring)

Zwei getrennte Update-Pfade:
  1. update_parqet()         → Positionen, Cash, Stückzahl, Einkaufspreis (Parqet API)
  2. update_yfinance_prices() → Tagesaktuelle Kurse + Daily Changes (yFinance)

FMP/Technical werden erst beim 16:15 Full-Refresh geladen.
Extrahiert aus services/refresh.py für bessere Modularität.
"""
import logging
from datetime import datetime

from state import portfolio_data, refresh_lock, YFINANCE_ALIASES, TZ_BERLIN
from models import PortfolioSummary, StockFullData
from fetchers.parqet import fetch_portfolio
from fetchers.yfinance_data import quick_price_update
from services.currency_converter import CurrencyConverter
from engine.history import save_snapshot

logger = logging.getLogger(__name__)


def calc_portfolio_totals(stocks: list) -> dict:
    """Berechnet Portfolio-Gesamtwerte und tägliche Veränderung.

    Zentraler Helper — vermeidet Code-Duplikation in refresh.py,
    update_parqet() und update_yfinance_prices().

    Returns:
        Dict mit total_value, total_cost, total_pnl, total_pnl_pct,
        daily_total_eur, daily_total_pct
    """
    total_value = sum(s.position.current_value for s in stocks)
    total_cost = sum(s.position.total_cost for s in stocks)
    total_pnl = total_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0

    daily_total_eur = 0.0
    for s in stocks:
        pct = s.position.daily_change_pct
        if pct is not None and s.position.ticker != "CASH":
            daily_total_eur += s.position.current_value * pct / (100 + pct)
    daily_total_pct = (
        (daily_total_eur / (total_value - daily_total_eur) * 100)
        if (total_value - daily_total_eur) > 0 else 0
    )

    return {
        "total_value": round(total_value, 2),
        "total_cost": round(total_cost, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl_pct, 1),
        "daily_total_eur": round(daily_total_eur, 2),
        "daily_total_pct": round(daily_total_pct, 2),
    }


async def update_parqet() -> dict:
    """Parqet-only Update: Positionen, Cash, Stückzahl, Einkaufspreis.

    Lädt NUR die Portfolio-Struktur von der Parqet API.
    Preise kommen von Parqet Performance API (Vortagesschluss).
    Kein yFinance, kein FMP — dauert nur 2-5 Sekunden.
    """
    if refresh_lock.locked():
        logger.info("Update bereits aktiv - überspringe")
        return {"status": "already_running"}

    async with refresh_lock:
        portfolio_data["refreshing"] = True
        try:
            logger.info("🔄 Parqet-Update gestartet (nur Positionen)...")

            # 1. Fetch positions from Parqet API
            positions = await fetch_portfolio()
            if not positions:
                logger.error("Keine Positionen von Parqet erhalten")
                return {"status": "error", "message": "Keine Positionen"}

            logger.info(f"📊 {len(positions)} Positionen von Parqet geladen")

            # 2. Wechselkurse zentral laden
            converter = await CurrencyConverter.create()
            eur_usd_rate = converter.rates.eur_usd

            # 3. Fetch stock names from yfinance (schnell, nutzt Cache)
            name_map = await _fetch_stock_names(positions)

            # 4. Build StockFullData with merged previous analysis
            prev_summary = portfolio_data.get("summary")
            prev_stocks_map = {}
            if prev_summary and prev_summary.stocks:
                prev_stocks_map = {ps.position.ticker: ps for ps in prev_summary.stocks}

            stocks = []
            for pos in positions:
                # Preise vom Parqet Performance API (bereits in EUR)
                _apply_metadata_only(pos, name_map, converter, prev_stocks_map)

                prev = prev_stocks_map.get(pos.ticker)
                if prev:
                    # Merge vorherige Daily Changes
                    if prev.position.daily_change_pct is not None:
                        pos.daily_change_pct = prev.position.daily_change_pct
                    stocks.append(StockFullData(
                        position=pos,
                        score=prev.score,
                        fundamentals=prev.fundamentals,
                        analyst=prev.analyst,
                        technical=prev.technical,
                        yfinance=prev.yfinance,
                        fmp_rating=prev.fmp_rating,
                        data_sources=prev.data_sources,
                        dividend=prev.dividend,
                    ))
                else:
                    stocks.append(StockFullData(position=pos))

            # 5. Calculate totals
            t = calc_portfolio_totals(stocks)

            # 6. Build summary
            prev_scores = [s.score for s in stocks if s.score]
            summary = PortfolioSummary(
                total_value=t["total_value"],
                total_cost=t["total_cost"],
                total_pnl=t["total_pnl"],
                total_pnl_percent=t["total_pnl_pct"],
                num_positions=len(stocks),
                stocks=stocks,
                scores=prev_scores,
                rebalancing=prev_summary.rebalancing if prev_summary else None,
                tech_picks=prev_summary.tech_picks if prev_summary else [],
                fear_greed=prev_summary.fear_greed if prev_summary else None,
                eur_usd_rate=eur_usd_rate,
                display_currency="EUR",
                daily_total_change=t["daily_total_eur"],
                daily_total_change_pct=t["daily_total_pct"],
            )

            portfolio_data["summary"] = summary
            portfolio_data["last_refresh"] = datetime.now(tz=TZ_BERLIN)

            cash_eur = next(
                (s.position.current_price for s in stocks if s.position.ticker == "CASH"), 0.0
            )

            logger.info(
                f"✅ Parqet-Update abgeschlossen: {len(stocks)} Positionen, "
                f"Gesamt: {total_value:,.2f} EUR (Cash: {cash_eur:,.2f} EUR)"
            )

            return {
                "status": "done",
                "positions": len(stocks),
                "total_eur": round(total_value, 2),
                "cash_eur": round(cash_eur, 2),
                "eur_usd_rate": eur_usd_rate,
            }

        except Exception as e:
            logger.error(f"❌ Parqet-Update fehlgeschlagen: {e}")
            import traceback
            traceback.print_exc()
            return {"status": "error", "message": str(e)}
        finally:
            portfolio_data["refreshing"] = False


async def update_yfinance_prices() -> dict:
    """yFinance Kurs-Update: Aktuelle Preise + Daily Changes.

    Lädt tagesaktuelle Kurse und Tagesänderungen für alle Positionen.
    Unabhängig von Parqet und FMP — kann jederzeit aufgerufen werden.
    """
    summary = portfolio_data.get("summary")
    if not summary or not summary.stocks:
        logger.warning("Kein Portfolio vorhanden — yFinance-Update übersprungen")
        return {"status": "no_portfolio"}

    try:
        logger.info("📈 yFinance Kurs-Update gestartet...")

        # Wechselkurse laden
        converter = await CurrencyConverter.create()

        # Alle Aktien-Ticker sammeln (kein CASH)
        stock_tickers = [s.position.ticker for s in summary.stocks if s.position.ticker != "CASH"]
        ticker_to_yf = {t: YFINANCE_ALIASES.get(t, t) for t in stock_tickers}
        yf_tickers = list(set(ticker_to_yf.values()))
        logger.debug(f"yf_tickers={yf_tickers[:5]}... ({len(yf_tickers)} total)")

        # 1. Batch-Download: Preise + Daily Changes
        prices_raw, daily_raw = await quick_price_update(yf_tickers) if yf_tickers else ({}, {})
        logger.debug(f"prices_raw={len(prices_raw)} daily_raw={len(daily_raw)}")

        # Map zurück auf Original-Ticker
        prices = {}
        daily_changes = {}
        for orig, yf_t in ticker_to_yf.items():
            if yf_t in prices_raw:
                prices[orig] = prices_raw[yf_t]
            if yf_t in daily_raw:
                daily_changes[orig] = daily_raw[yf_t]
        logger.debug(f"mapped prices={len(prices)} daily={len(daily_changes)}")

        # 2. ISIN-basierte Ticker Fallback
        isin_positions = [s.position for s in summary.stocks
                         if s.position.ticker not in prices
                         and len(s.position.ticker) == 12
                         and s.position.ticker[:2].isalpha()]
        await _fetch_isin_prices(isin_positions, prices, daily_changes)

        # 3. Preise + Daily Changes auf Positionen anwenden
        updated = 0
        total_value = 0.0
        total_cost = 0.0

        for stock in summary.stocks:
            pos = stock.position
            if pos.ticker == "CASH":
                total_value += pos.current_value
                total_cost += pos.total_cost
                continue

            # Aktuellen Kurs setzen (yFinance → EUR)
            if pos.ticker in prices and prices[pos.ticker] > 0:
                raw_price = prices[pos.ticker]
                pos.current_price = converter.to_eur(raw_price, pos.ticker)
                pos.price_currency = "EUR"
                updated += 1

            # Daily Change setzen
            if pos.ticker in daily_changes:
                pos.daily_change_pct = daily_changes[pos.ticker]

            total_value += pos.current_value
            total_cost += pos.total_cost

        # 4. Summary-Werte aktualisieren
        t = calc_portfolio_totals(list(summary.stocks))
        summary.total_value = t["total_value"]
        summary.total_cost = t["total_cost"]
        summary.total_pnl = t["total_pnl"]
        summary.total_pnl_percent = t["total_pnl_pct"]
        summary.daily_total_change = t["daily_total_eur"]
        summary.daily_total_change_pct = t["daily_total_pct"]
        summary.last_updated = datetime.now(tz=TZ_BERLIN)

        logger.info(
            f"📈 yFinance-Update: {updated}/{len(stock_tickers)} Kurse, "
            f"{len(daily_changes)}/{len(stock_tickers)} Daily Changes"
        )

        return {
            "status": "done",
            "prices_updated": updated,
            "daily_changes": len(daily_changes),
        }

    except Exception as e:
        logger.warning(f"yFinance Kurs-Update fehlgeschlagen: {e}")
        return {"status": "error", "message": str(e)}


# ─────────────────────────────────────────────────────────────
# Hilfsfunktionen
# ─────────────────────────────────────────────────────────────

async def _fetch_isin_prices(stock_positions, prices, daily_changes):
    """Holt Preise für ISIN-basierte Ticker via yfinance."""
    for p in stock_positions:
        if p.ticker not in prices and len(p.ticker) == 12 and p.ticker[:2].isalpha():
            try:
                import yfinance as yf
                t = yf.Ticker(p.ticker)
                hist = t.history(period="5d")
                if hist is not None and not hist.empty:
                    closes = hist["Close"].dropna()
                    prices[p.ticker] = round(float(closes.iloc[-1]), 2)
                    if len(closes) >= 2:
                        prev = float(closes.iloc[-2])
                        if prev > 0:
                            daily_changes[p.ticker] = round(((float(closes.iloc[-1]) - prev) / prev) * 100, 2)
            except Exception:
                pass


async def _fetch_stock_names(positions) -> dict:
    """Holt Aktiennamen aus yfinance."""
    name_map = {}
    try:
        import yfinance as yf
        for pos in positions:
            if pos.ticker == "CASH" or (pos.name and pos.name != pos.ticker):
                continue
            yf_ticker = YFINANCE_ALIASES.get(pos.ticker, pos.ticker)
            if len(yf_ticker) == 12 and yf_ticker[:2].isalpha():
                continue
            try:
                t = yf.Ticker(yf_ticker)
                info = t.info or {}
                sn = info.get("shortName") or info.get("longName")
                if sn:
                    name_map[pos.ticker] = sn
            except Exception:
                pass
    except Exception:
        pass
    return name_map


def _apply_metadata_only(pos, name_map, converter, prev_stocks_map):
    """Wendet nur Metadaten (Name, Sektor) auf eine Position an. Keine Preisänderung."""
    if pos.ticker == "CASH":
        pos.price_currency = "EUR"
        return

    # Preis von Parqet Performance API (bereits in EUR)
    # → KEINE Konvertierung nötig (Parqet liefert Portfolio-Währung)
    pos.price_currency = "EUR"

    # Name from yfinance
    if pos.ticker in name_map:
        pos.name = name_map[pos.ticker]

    # Merge previous data
    prev = prev_stocks_map.get(pos.ticker)
    if prev:
        if prev.position.sector and (not pos.sector or pos.sector == "Unknown"):
            pos.sector = prev.position.sector
        if prev.position.name and (not pos.name or pos.name == pos.ticker):
            pos.name = prev.position.name
