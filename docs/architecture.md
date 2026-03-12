# FinanzBro – Architektur

## Übersicht

FinanzBro ist ein intelligentes Aktienportfolio-Dashboard mit automatisierter Multi-Faktor-Analyse.  
Läuft lokal (Python) und auf Google Cloud Run (Docker).

```
FinanzBro/
├── main.py                 # FastAPI App + Lifespan + Scheduler
├── config.py               # Pydantic Settings v2 (.env auto-loading)
├── models.py               # 31 Pydantic-Datenmodelle
├── state.py                # Globaler State + Refresh-Progress
├── database.py             # SQLite Persistenz (WAL, Score-History, Snapshots)
├── cache_manager.py        # Thread-safe Memory+Disk Cache
├── logging_config.py       # structlog (JSON in Production, Console in Dev)
│
├── routes/
│   ├── portfolio.py        # GET /api/portfolio, /api/stock/{ticker}
│   ├── refresh.py          # POST /api/refresh + GET /api/refresh/status
│   ├── analysis.py         # POST /api/analysis/run, GET /api/analysis/latest
│   ├── analytics.py        # Dividenden, Risiko, Korrelation, Attribution
│   ├── parqet_oauth.py     # GET /api/parqet/authorize + /callback (OAuth2 PKCE)
│   ├── streaming.py        # GET /api/prices/stream (SSE)
│   └── telegram.py         # Telegram Webhook
│
├── services/
│   ├── refresh.py          # Voller Refresh (mit Progress-Tracking)
│   ├── data_loader.py      # Paralleles Batch-Loading (4er Batches)
│   ├── currency_converter.py # Zentrale EUR-Konvertierung
│   ├── ai_agent.py         # Gemini AI + Telegram Reports
│   ├── telegram.py         # Telegram Bot API
│   ├── telegram_bot.py     # Command-Router + Handler
│   ├── vertex_ai.py        # Gemini Client + Daily Limit + Context Cache
│   ├── earnings_ai.py      # Earnings-Analyse (Gemini Pro + Search)
│   ├── score_commentary.py # AI Score-Kommentare (Flash)
│   ├── weekly_digest.py    # Wöchentlicher Digest (Flash)
│   ├── tech_radar_ai.py    # AI-gestützte Tech-Empfehlungen
│   └── analyst_tracker.py  # Analysten Track Record Bewertung
│
├── engine/
│   ├── scorer.py           # 10-Faktor Scoring Engine
│   ├── rebalancer.py       # Portfolio-Rebalancing
│   ├── analysis.py         # Analyse-Reports → SQLite
│   ├── analytics.py        # Korrelation, Risiko, Dividenden
│   ├── attribution.py      # P&L Attribution (Sektor, Herfindahl-Index)
│   ├── history.py          # Portfolio-Snapshots → SQLite
│   └── backtest.py         # Score-Backtest Engine
│
├── fetchers/
│   ├── parqet.py           # Parqet Connect API (Performance + Activities)
│   ├── parqet_auth.py      # OAuth2 Token-Management (PKCE, Refresh)
│   ├── fmp.py              # Financial Modeling Prep API
│   ├── yfinance_data.py    # yFinance (Batch-Download)
│   ├── finnhub_ws.py       # Finnhub WebSocket (Echtzeit US)
│   ├── technical.py        # RSI, SMA, MACD Berechnung
│   ├── fear_greed.py       # CNN Fear & Greed Index
│   ├── currency.py         # EUR/USD/DKK/GBP Wechselkurse
│   └── demo_data.py        # Synthetische Demo-Daten
│
├── static/                 # Frontend (HTML/JS/CSS)
└── tests/                  # 227 pytest Tests
```

## Datenfluss

```mermaid
sequenceDiagram
    participant U as User/Browser
    participant R as routes/
    participant S as services/refresh
    participant DL as services/data_loader
    participant F as fetchers/
    participant E as engine/
    participant DB as database.py
    participant AI as Vertex AI

    U->>R: POST /api/refresh
    R->>S: _refresh_data()
    S->>F: fetch_portfolio() [Parqet]
    F-->>S: 20 Positionen (19 Aktien + Cash)
    S->>DL: load_positions_batched()
    DL->>F: FMP + yFinance + Technical (parallel)
    F-->>DL: Fundamentals, Preise, Indikatoren
    DL->>E: calculate_score() [10 Faktoren]
    E-->>S: StockScore + StockFullData
    S->>E: calculate_rebalancing()
    S->>DB: save_snapshot() + save_analysis()
    S->>AI: Score-Kommentare (Flash)
    S->>AI: Daily Report (Pro)
    S-->>R: PortfolioSummary
    R-->>U: JSON Response
```

## Persistenz-Schichten

| Schicht | Technologie | Inhalt | Verlust bei Restart? |
|---------|------------|--------|---------------------|
| **SQLite** (`finanzbro.db`) | WAL-Modus | Score-History, Snapshots, Reports | Ja (Cloud Run) |
| **JSON Cache** | Memory + Disk | FMP, yFinance, Parqet | Teilweise (volatile) |
| **State** (`portfolio_data`) | In-Memory Dict | Aktuelles Portfolio, Activities | Ja |

> **Cloud Run Hinweis:** SQLite-Daten gehen bei Container-Restart verloren. Für Langzeit-Persistenz: Litestream → GCS Backup.

## AI-Architektur (Vertex AI)

```mermaid
graph LR
    A[vertex_ai.py] --> B{Konfiguriert?}
    B -->|GCP_PROJECT_ID| C[Vertex AI Client FA]
    B -->|GEMINI_API_KEY| D[API Key Fallback]
    B -->|Weder noch| E[AI deaktiviert]
    
    C --> F[Daily Limit: 100/Tag]
    D --> F
    F --> G[Flash: Score-Kommentare]
    F --> H[Flash: Weekly Digest]
    F --> I[Pro + Search: Earnings]
    F --> J[Pro + Search: Risk]
    F --> K[Pro + Search: Chat]
```

## Caching-Strategie

| Cache-Typ | Verhalten | Beispiele |
|-----------|-----------|-----------|
| **Volatile** | Beim Start gelöscht | Fear&Greed, Technical |
| **Persistent** | Bleibt erhalten | Parqet, Currency, FMP, yFinance |
| **State-Level** | Im Memory nach Refresh | Activities, Portfolio Summary |

## Cloud Run Deployment

```
Docker Image (python:3.12-slim, 1 Worker)
  ├── App-Code + SQLite DB
  ├── cache/ (Stale Cache Fallback)
  └── Env-Vars (API Keys, OAuth2 Tokens)

Konfiguration:
  Memory:        512 Mi
  CPU:           1
  Min Instances: 0 (Scale to Zero)
  Max Instances: 1
  Region:        europe-west1
```

### Scheduler (APScheduler)

| Job | Zeit | Funktion |
|-----|------|----------|
| Full Analyse | 16:15 CET | Refresh + Scoring + AI Report |
| Intraday Kurse | alle 15min Mo-Fr 8-22h | yFinance Batch |
| Weekly Digest | Sonntag 18:00 | KI-Zusammenfassung |
