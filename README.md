# 📊 FinanzBro – Intelligentes Portfolio Dashboard

Echtzeit-Portfolio-Dashboard mit Multi-Faktor-Scoring, Conviction-basiertem Rebalancing, AI Trade Advisor (Function Calling) und Gemini Structured Output.  
Läuft lokal und auf **Google Cloud Run**.

## Architektur

```
Browser (HTML/JS/CSS)
    ↕ REST API + SSE
FastAPI Backend (lokal / Cloud Run)
    ├── routes/          → API-Endpunkte
    ├── engine/          → Scoring, Analyse, Rebalancing, Attribution
    ├── services/        → Refresh, AI Agent, Telegram Bot, Vertex AI
    ├── fetchers/        → Datenquellen (Parqet, FMP, yfinance, Finnhub)
    ├── database.py      → SQLite Persistenz (WAL, Score-History, Snapshots)
    └── cache/           → In-Memory + Disk Caches
```

## Datenquellen

| Quelle | Modul | Auth | Liefert |
|---|---|---|---|
| **Parqet** | `fetchers/parqet.py` | OAuth2 / JWT | Portfolio-Positionen, Kaufkurse, Sektoren |
| **FMP** | `fetchers/fmp.py` | `FMP_API_KEY` | Fundamentals, Analysten, Dividenden, News, Earnings |
| **yfinance** | `fetchers/yfinance_data.py` | – | Kurse, Recommendations, Insider, ESG, Earnings, Fundamentals-Fallback |
| **Finnhub** | `fetchers/finnhub_ws.py` | `FINNHUB_API_KEY` | Echtzeit-Kurse (WebSocket, nur US) |
| **yFinance WS** | `fetchers/yfinance_ws.py` | – | Echtzeit-Kurse (WebSocket, International/EU) |
| **CNN** | `fetchers/fear_greed.py` | – | Fear & Greed Index |
| **Vertex AI** | `services/vertex_ai.py` | GCP Service Account | Gemini Pro/Flash, Search Grounding |

> FMP Free Tier: 250 Requests/Tag. Alle anderen Quellen sind kostenlos.

## Scoring Engine (`engine/scorer.py`)

10-Faktor-Bewertungssystem (0–100 Score):

| Faktor | Gewicht | Quelle |
|---|---|---|
| Quality (ROE, Margins, Debt) | 19% | FMP |
| Analyst Consensus + Kursziele | 15% | FMP (verifiziert via Track Record) |
| Valuation (P/E, EV/EBITDA, PEG) | 14% | FMP |
| Technical (RSI, SMA, Momentum) | 13% | yfinance |
| Growth (Revenue, Earnings YoY) | 11% | FMP + yfinance |
| Quantitative (Altman Z, Piotroski) | 10% | FMP |
| Market Sentiment (Fear&Greed) | 7% | CNN |
| Momentum (90d, 180d) | 6% | yfinance |
| Insider Trading | 3% | yfinance (v1.2.0: `Text`-Spalte) |
| ESG Risk | 2% | yfinance (`sustainability` + `info` Fallback) |

**Rating:** Buy (≥68), Hold (40–67), Sell (<40)

## AI Features (Vertex AI / Gemini)

| Feature | Modell | Beschreibung |
|---------|--------|--------------|
| **AI Trade Advisor** | Pro + Grounding + **Function Calling** | 🧠 Agentischer Advisor — Gemini ruft selbst Tools auf |
| Score-Kommentare | Flash + **Structured Output** | KI-Kommentar pro Aktie bei jedem Refresh |
| Earnings-Analyse | Pro + Grounding + **Structured Output** | `/earnings` — Echtzeit-Earnings via Search |
| Portfolio-Chat | Pro + Grounding | Freitext-Fragen in Telegram |
| Weekly Digest | Flash | Wöchentlicher Summary (Sonntag 18:00) |
| Risiko-Szenarien | Pro + Grounding | `/risk` — AI-basierte Stress-Analyse |
| Performance Attribution | Engine | P&L nach Sektor, Top/Flop, Herfindahl-Index |

### Function Calling (Trade Advisor)
Gemini 2.5 Pro hat Zugriff auf 3 Tools und entscheidet selbst, welche Daten benötigt werden:
- `get_stock_score(ticker)` — 10-Faktor-Score berechnen
- `get_portfolio_overview()` — Portfolio-Kontext abrufen
- `get_sector_impact(ticker, action, amount)` — Sektor-Impact simulieren

### Structured Output
Alle JSON-AI-Services nutzen `response_schema` — Gemini garantiert valides JSON.

## Rebalancing Engine v3 (`engine/rebalancer.py`)

| Feature | Beschreibung |
|---------|-------------|
| Cash-Reserve (R1) | Min. 5% Cash wird nie investiert |
| Gesamt-Portfolio-Basis (R2) | `total_value` inkl. Cash → realistische Gewichte |
| Investierbares Cash (R3) | Kaufempfehlungen auf verfügbares Cash begrenzt |
| Conviction Sizing (R4) | High (≥70): 1.5×, Mid (45-69): 1.0×, Low (<45): 0.6× |
| Portfolio-Health-Score (R5) | 0-100 Score: HHI, Sektor, Beta, Qualität, Positions-Count |

## Telegram Bot (`/help` für alle Befehle)

| Befehl | Beschreibung |
|--------|--------------|
| `/portfolio` | Portfolio-Übersicht |
| `/score [TICKER]` | Score + AI-Kommentar |
| `/refresh` | Daten-Refresh starten |
| `/attribution` | P&L Attribution (Sektor, Top/Flop) |
| `/earnings [TICKER]` | Earnings-Analyse (AI) |
| `/risk` | Risiko-Szenarien (AI) |
| Freitext | Portfolio-Chat (AI) |

## API-Endpoints

### Portfolio (`routes/portfolio.py`)
| Methode | Pfad | Beschreibung |
|---|---|---|
| GET | `/` | Dashboard (HTML) |
| GET | `/api/portfolio` | Portfolio-Daten (JSON) |
| GET | `/api/stock/{ticker}` | Einzelaktie Details |
| GET | `/api/portfolio/history` | Portfolio-Wert-Entwicklung |
| GET | `/api/rebalancing` | Rebalancing-Empfehlungen |
| GET | `/api/tech-picks` | Tech-Aktien Screening |
| GET | `/api/fear-greed` | Fear & Greed Index |
| GET | `/api/status` | System-Status |

### Refresh (`routes/refresh.py`)
| Methode | Pfad | Beschreibung |
|---|---|---|
| POST | `/api/refresh` | Kompletter Refresh |
| POST | `/api/refresh/prices` | Nur Kurse updaten |
| POST | `/api/refresh/parqet` | Nur Parqet-Positionen |
| POST | `/api/refresh/scores` | Nur Scores neuberechnen |
| GET | `/api/refresh/status` | Refresh-Fortschritt |

### Analytics (`routes/analytics.py`)
| Methode | Pfad | Beschreibung |
|---|---|---|
| GET | `/api/market-indices` | S&P 500, Nasdaq, DAX |
| GET | `/api/movers` | Top Gewinner/Verlierer |
| GET | `/api/heatmap` | Portfolio-Treemap |
| GET | `/api/dividends` | Dividenden-Übersicht |
| GET | `/api/benchmark` | Benchmark-Vergleich |
| GET | `/api/correlation` | Korrelationsmatrix |
| GET | `/api/risk` | Beta, VaR, Max Drawdown |
| GET | `/api/attribution` | P&L Attribution |

## Persistenz

| Speicher | Technologie | Inhalt |
|----------|------------|--------|
| SQLite (`finanzbro.db`) | WAL-Modus, Thread-safe | Score-History, Snapshots, Reports |
| JSON Cache | Memory + Disk | FMP, yFinance, Fear&Greed (volatile) |
| Parqet Cache | Memory + Disk | Positionen, Tokens (persistent) |

## Deployment

### Lokal
```bash
python -m venv venv
pip install -r requirements.txt
python main.py  # → http://localhost:8000
```

### Cloud Run (Windows)
```powershell
gcloud.cmd run deploy finanzbro --source . --region europe-west1 --allow-unauthenticated --memory 512Mi --timeout 300 --update-env-vars ENVIRONMENT=production,GCP_PROJECT_ID=job-automation-jonas
```

### Environment (.env)
```env
# Pflicht
FMP_API_KEY=...
PARQET_PORTFOLIO_ID=...

# Optional (Erweiterte Features)
FINNHUB_API_KEY=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
GEMINI_API_KEY=...

# Cloud Run (automatisch)
ENVIRONMENT=production
GCP_PROJECT_ID=...
```

### Scheduler

| Job | Zeit | Funktion |
|-----|------|----------|
| Full Analyse | 16:15 | Refresh + Scoring + AI Report |
| Intraday Kurse | alle 15min (Mo-Fr) | yFinance Batch |
| Weekly Digest | Freitag 22:30 | Wöchentliche KI-Zusammenfassung |

## Projektstruktur

```
FinanzBro/
├── main.py              # FastAPI App + Startup + Scheduler
├── config.py            # Pydantic Settings v2
├── models.py            # 31 Pydantic-Modelle
├── state.py             # Globaler App-State
├── database.py          # SQLite Persistence (WAL, 3 Tabellen)
├── cache_manager.py     # Memory+Disk Cache
├── logging_config.py    # structlog (JSON/Console)
├── Dockerfile           # Cloud Run Container
├── engine/
│   ├── scorer.py        # 10-Faktor Score-Berechnung
│   ├── analysis.py      # Report-Generierung + Score-Historie
│   ├── analytics.py     # Korrelation, Risiko, Dividenden
│   ├── rebalancer.py    # Rebalancing-Empfehlungen
│   ├── attribution.py   # P&L Attribution + Herfindahl-Index
│   ├── history.py       # Portfolio-Snapshots → SQLite
│   └── backtest.py      # Score-Backtest Engine
├── fetchers/
│   ├── parqet.py        # Parqet Connect API (OAuth2 PKCE)
│   ├── parqet_auth.py   # Token-Management
│   ├── fmp.py           # Financial Modeling Prep
│   ├── yfinance_data.py # Yahoo Finance (Batch)
│   ├── yfinance_ws.py   # yFinance WebSocket (Echtzeit International)
│   ├── finnhub_ws.py    # Finnhub WebSocket (Echtzeit US)
│   ├── technical.py     # RSI, SMA, MACD
│   ├── fear_greed.py    # CNN Fear & Greed
│   ├── currency.py      # Wechselkurse
│   └── demo_data.py     # Demo-Daten
├── services/
│   ├── refresh.py       # Haupt-Refresh (mit Progress-Tracking)
│   ├── data_loader.py   # Paralleles Batch-Loading
│   ├── ai_agent.py      # Täglicher AI Telegram-Report
│   ├── telegram.py      # Telegram API
│   ├── telegram_bot.py  # Telegram Bot (Command-Handler)
│   ├── vertex_ai.py     # Gemini Client + Context Caching
│   ├── trade_advisor.py # AI Trade Advisor (Function Calling + Structured Output)
│   ├── earnings_ai.py   # Earnings-Analyse (Structured Output)
│   ├── score_commentary.py  # AI Score-Kommentare (Structured Output)
│   ├── weekly_digest.py # Wöchentlicher Digest (Flash)
│   ├── tech_radar_ai.py # Tech-Empfehlungen (AI)
│   ├── analyst_tracker.py   # Analysten Track Record
│   └── currency_converter.py
├── routes/
│   ├── portfolio.py     # Portfolio + Dashboard
│   ├── refresh.py       # Refresh + Status
│   ├── analysis.py      # Analyse-Reports
│   ├── analytics.py     # Erweiterte Analysen + Attribution
│   ├── parqet_oauth.py  # OAuth2 PKCE
│   ├── streaming.py     # SSE Preis-Stream
│   └── telegram.py      # Telegram Webhook
├── static/
│   ├── index.html       # Dashboard UI
│   ├── app.js           # Frontend-Logic
│   └── styles.css       # Styling
└── tests/               # 300+ pytest Tests
```
