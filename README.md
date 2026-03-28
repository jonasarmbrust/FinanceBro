# 📊 FinanzBro – Intelligent Portfolio Dashboard

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB.svg?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Gemini AI](https://img.shields.io/badge/Gemini_AI-2.5_Pro-4285F4.svg?logo=google&logoColor=white)](https://ai.google.dev)
[![Cloud Run](https://img.shields.io/badge/Cloud_Run-Deployed-4285F4.svg?logo=googlecloud&logoColor=white)](https://cloud.google.com/run)
[![Tests](https://img.shields.io/badge/Tests-368%2B-22c55e.svg)](tests/)
[![CI/CD](https://github.com/jonasarmbrust/FinanzBro/actions/workflows/deploy.yml/badge.svg)](https://github.com/jonasarmbrust/FinanzBro/actions)

> **Your portfolio. Your rules. Powered by AI.**

A full-stack portfolio dashboard combining real-time market data, fundamental analysis, and AI-driven recommendations in a modern web interface. Runs locally or on **Google Cloud Run** — and acts autonomously: proactive Telegram alerts on market-relevant events, daily AI reports, and a Telegram bot that responds to voice and text messages.

![FinanzBro Dashboard](docs/screenshots/dashboard-overview.png)

## ✨ Highlights

🎯 **10-Factor Scoring Engine** — Quality, Valuation, Technical, Growth, Analysts, Sentiment, Insider, ESG, Quantitative + Stability → one composite score per stock (0–100)

🤖 **AI Trade Advisor** — Ask Gemini 2.5 Pro: *"Should I buy NVDA for €2,000?"* → get a detailed analysis with position sizing, risk assessment, and conviction score

⚖️ **Conviction-Based Rebalancing** — Not simple equal-weight, but weighted recommendations based on score, sector limits (max 35%), beta, and analyst consensus

📡 **Live Streaming** — yFinance WebSocket + Server-Sent Events → prices update in real-time without page reload

📱 **Telegram Bot** — Daily AI-generated portfolio reports, weekly digests, proactive news alerts, and voice commands → your portfolio always in your pocket

🔍 **Tech Radar** — Automated stock screener discovers new tech stocks daily, scores them with the multi-factor model, and delivers AI-generated summaries

📊 **Deep Analytics** — Sector allocation, benchmark vs. S&P 500, correlation matrix, risk profile (VaR, beta, drawdown), dividend tracker, earnings calendar, P&L attribution

🔄 **Fully Autonomous** — APScheduler handles it all: price updates every 15 min, daily analysis at 16:15, weekly digest, news curator 4x daily

📄 **CSV Portfolio Import** — No Parqet account? Import your portfolio from any CSV file with ticker, shares, and buy price. Works with any broker export.

🌐 **Bilingual UI** — Switch between English and German with one click. Language preference is saved automatically.

## 🛠️ Tech Stack

| Layer | Technologies |
|---|---|
| **Backend** | Python 3.12, FastAPI, Uvicorn, Pydantic, APScheduler |
| **AI** | Google Gemini 2.5 Pro + Flash (Function Calling, Structured Output, Context Caching) |
| **Data** | Parqet API (OAuth2/PKCE), CSV Import, FMP API, yFinance, CNN Fear & Greed |
| **Frontend** | Vanilla HTML/JS/CSS, Chart.js, SSE Streaming, Dark/Light Mode, i18n (DE/EN) |
| **Infrastructure** | Docker, Google Cloud Run (Service + Job), SQLite |
| **Bot** | Telegram Bot API (Commands, Voice Input, Inline Buttons) |
| **Tests** | pytest (390+ tests, 22 test files) |

## 💡 Why I Built This

I built FinanzBro to answer a simple question: **Can a non-engineer build a production-grade AI agent system from scratch?**

The answer turned out to be *yes* — and the journey taught me more about AI's real capabilities than any course. I chose personal investing as my domain because genuine interest keeps you going when things break at 2 AM. What started as a scoring engine evolved into an autonomous AI advisor with function calling, real-time streaming, and a Telegram bot that delivers daily AI-generated portfolio reports — turning this from a side project into an interactive agent I actually talk to every day.

## Screenshots

<table>
  <tr>
    <td><img src="docs/screenshots/portfolio-table.png" alt="Portfolio" width="500"/><br/><em>Portfolio positions with scoring</em></td>
    <td><img src="docs/screenshots/stock-detail.png" alt="Stock Detail" width="250"/><br/><em>Stock detail with score breakdown</em></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/analyse-tab.png" alt="Analysis" width="500"/><br/><em>Analysis: sectors, risk, benchmark, dividends</em></td>
    <td><img src="docs/screenshots/rebalancing.png" alt="Rebalancing" width="500"/><br/><em>Conviction-based rebalancing</em></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/tech-picks.png" alt="Tech Picks" width="500"/><br/><em>AI-powered tech recommendations</em></td>
    <td><img src="docs/screenshots/ai-advisor.png" alt="AI Advisor" width="500"/><br/><em>AI Trade Advisor (Gemini 2.5 Pro)</em></td>
  </tr>
</table>

### 🤖 Telegram Bot

<table>
  <tr>
    <td><img src="docs/screenshots/telegram-daily.jpg" alt="Daily Report" width="280"/><br/><em>Daily AI Report</em></td>
    <td><img src="docs/screenshots/telegram-weekly.jpg" alt="Weekly Digest" width="280"/><br/><em>Weekly Digest</em></td>
    <td><img src="docs/screenshots/telegram-news.jpg" alt="News Alert" width="280"/><br/><em>Proactive News Alerts</em></td>
  </tr>
</table>

## Architecture

```
Browser (HTML/JS/CSS)
    ↕ REST API + SSE
FastAPI Backend (local / Cloud Run)
    ├── routes/          → API endpoints
    ├── engine/          → Scoring, analysis, rebalancing, attribution
    ├── services/        → Refresh, AI agent, Telegram bot, Vertex AI
    ├── fetchers/        → Data sources (Parqet, FMP, yfinance)
    ├── database.py      → SQLite persistence (WAL, score history, snapshots)
    └── cache/           → In-memory + disk caches
```

## Data Sources

| Source | Module | Auth | Provides |
|---|---|---|---|
| **Parqet** | `fetchers/parqet.py` | OAuth2 / JWT | Portfolio positions, cost basis, sectors |
| **FMP** | `fetchers/fmp.py` | `FMP_API_KEY` | Fundamentals, analysts, dividends, news (6h cache protection) |
| **yfinance** | `fetchers/yfinance_data.py` | – | Prices, recommendations, insider, ESG, earnings surprise, Altman Z, Piotroski |
| **yFinance WS** | `fetchers/yfinance_ws.py` | – | Real-time prices (WebSocket, international) |
| **yFinance Screener** | `fetchers/yfinance_screener.py` | – | Stock discovery (EquityQuery) |
| **CNN** | `fetchers/fear_greed.py` | – | Fear & Greed Index |
| **Vertex AI** | `services/vertex_ai.py` | GCP Service Account | Gemini Pro/Flash, Search Grounding |

> FMP Free Tier: 250 requests/day with 6h cache protection. All other sources are free.

## Scoring Engine (`engine/scorer.py`)

10-factor scoring system (0–100 composite score):

| Factor | Weight | Source |
|---|---|---|
| Quality (ROE, Margins, Debt) | 19% | FMP |
| Analyst Consensus + Price Targets | 15% | FMP (verified via track record) |
| Valuation (P/E, EV/EBITDA, PEG) | 14% | FMP |
| Technical (RSI, SMA, Momentum) | 13% | yfinance |
| Growth (Revenue, Earnings YoY, Beat Rate) | 11% | FMP + yfinance (Earnings Surprise) |
| Quantitative (Altman Z, Piotroski) | 10% | yfinance (self-calculated) |
| Market Sentiment (Fear&Greed) | 7% | CNN |
| Momentum (90d, 180d) | 6% | yfinance |
| Insider Trading | 3% | yfinance |
| ESG Risk | 2% | yfinance (`sustainability` + `info` fallback) |

**Rating:** Buy (≥68), Hold (40–67), Sell (<40)

## AI Features (Vertex AI / Gemini)

| Feature | Model | Description |
|---------|-------|-------------|
| **AI Trade Advisor** | Pro + Grounding + **Function Calling** | 🧠 Agentic advisor — Gemini autonomously calls tools |
| **AI Chat** | Pro + **Function Calling** | 💬 Free-form portfolio discussion in browser |
| **Voice-to-Action** | Pro + **Function Calling** + Audio | 🎙️ Voice messages natively to Gemini (Telegram) |
| **News Curator** | Flash + Grounding + **Structured Output** | 📡 Proactive portfolio news alerts (4×/day) |
| Score Commentaries | Flash + **Structured Output** | AI commentary per stock on each refresh |
| Earnings Analysis | Pro + Grounding + **Structured Output** | `/earnings` — Real-time earnings via Search |
| Portfolio Chat | Pro + Grounding | Free-text questions in Telegram |
| Weekly Digest | Flash | Weekly summary (Sunday 18:00) |
| Risk Scenarios | Pro + Grounding | `/risk` — AI-powered stress analysis |
| Performance Attribution | Engine | P&L by sector, top/flop, Herfindahl Index |

### Function Calling (Trade Advisor)
Gemini 2.5 Pro has access to 3 tools and autonomously decides which data is needed:
- `get_stock_score(ticker)` — Calculate 10-factor score
- `get_portfolio_overview()` — Fetch portfolio context
- `get_sector_impact(ticker, action, amount)` — Simulate sector impact

### Async AI Integration
All Gemini API calls use the async SDK (`client.aio.models.generate_content`). This prevents blocking the FastAPI `asyncio` event loop during long AI inference times, ensuring the dashboard remains responsive at all times.

### Structured Output
All JSON-based AI services use `response_schema` — Gemini guarantees valid JSON output.

## Rebalancing Engine v3 (`engine/rebalancer.py`)

| Feature | Description |
|---------|-------------|
| Cash Reserve (R1) | Min. 5% cash is never invested |
| Total Portfolio Basis (R2) | `total_value` including cash → realistic weights |
| Investable Cash (R3) | Buy recommendations limited to available cash |
| Conviction Sizing (R4) | High (≥70): 1.5×, Mid (45-69): 1.0×, Low (<45): 0.6× |
| Portfolio Health Score (R5) | 0-100 score: HHI, sector, beta, quality, position count |

## Telegram Bot (`/help` for all commands)

| Command | Description |
|---------|-------------|
| `/portfolio` | Portfolio overview |
| `/score [TICKER]` | Score + AI commentary |
| `/refresh` | Trigger data refresh |
| `/attribution` | P&L attribution (sector, top/flop) |
| `/earnings [TICKER]` | Earnings analysis (AI) |
| `/risk` | Risk scenarios (AI) |
| `/news-alerts` | Check portfolio news (AI) |
| 🎙️ Voice message | Voice-to-action (AI) |
| Free text | Portfolio chat (AI) |

## API Endpoints

42+ REST endpoints, grouped into 6 modules:

| Module | Endpoints | Highlights |
|---|---|---|
| **Portfolio** | 11 | Dashboard, positions, sectors, Fear & Greed |
| **Analytics** | 13 | Benchmark, correlation, risk, dividends, heatmap |
| **AI Advisor** | 8 | Trade evaluation, chat, backtest, score trends |
| **Refresh** | 8 | Granular updates (prices, scores, reports) |
| **Demo** | 3 | Demo portfolio activate/deactivate |
| **Streaming** | 1 | SSE real-time prices |

📖 **[Full API Documentation →](docs/api.md)**

## Persistence

| Storage | Technology | Contents |
|---------|-----------|----------|
| SQLite (`finanzbro.db`) | WAL mode, thread-safe | Score history, snapshots, reports |
| JSON Cache | Memory + Disk | FMP, yFinance, Fear&Greed (volatile) |
| Parqet Cache | Memory + Disk | Positions, tokens (persistent) |

## Security

| Protection | Configuration |
|-----------|---------------|
| **Dashboard Password** | `DASHBOARD_USER` + `DASHBOARD_PASSWORD` in `.env` |
| **Telegram Webhook** | `TELEGRAM_WEBHOOK_SECRET` — secret in URL path |
| **Chat ID Filter** | Bot only responds to configured `TELEGRAM_CHAT_ID` |

## Deployment

### Local
```bash
python -m venv venv
pip install -r requirements.txt
python main.py  # → http://localhost:8000
```

### Cloud Run Service (Dashboard + Webhook)
```bash
./deploy.sh
```

### Cloud Run Job (daily Telegram report, free tier)
```bash
./deploy_job.sh  # Creates Job + Cloud Scheduler (15:45 CET)
```

### Environment (.env)
```env
# Required
FMP_API_KEY=...
PARQET_PORTFOLIO_ID=...

# Optional (Advanced Features)
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
GEMINI_API_KEY=...

# Security
DASHBOARD_USER=...
DASHBOARD_PASSWORD=...
TELEGRAM_WEBHOOK_SECRET=...

# Cloud Run (automatic)
ENVIRONMENT=production
GCP_PROJECT_ID=...
```

### Scheduler

| Job | Schedule | Function |
|-----|----------|----------|
| Full Analysis | 16:15 | Refresh + Scoring + AI Report |
| Intraday Prices | Every 15 min (Mon-Fri) | yFinance Batch |
| Weekly Digest | Friday 22:30 | Weekly AI summary |
| News Curator | 09, 13, 17, 21h (Mon-Fri) | Portfolio news alerts (Gemini Flash) |
| Cloud Run Job | 15:45 (Cloud Scheduler) | Full Refresh → Telegram Report |

## Project Structure

```
FinanzBro/
├── main.py              # FastAPI app + startup + scheduler
├── config.py            # Pydantic Settings v2
├── models.py            # 31 Pydantic models
├── state.py             # Global app state
├── database.py          # SQLite persistence (WAL, 3 tables)
├── cache_manager.py     # Memory + disk cache
├── logging_config.py    # structlog (JSON/Console)
├── Dockerfile           # Cloud Run Service container
├── Dockerfile.job       # Cloud Run Job container
├── run_job.py           # Job entry point (Refresh → Report)
├── middleware/
│   └── auth.py          # Basic Auth middleware
├── engine/
│   ├── scorer.py        # 10-factor score calculation
│   ├── analysis.py      # Report generation + score history
│   ├── analytics.py     # Correlation, risk, dividends
│   ├── rebalancer.py    # Rebalancing recommendations
│   ├── attribution.py   # P&L attribution + Herfindahl Index
│   ├── portfolio_history.py # Portfolio history (per-stock, cash, cost basis)
│   ├── history.py       # Portfolio snapshots → SQLite
│   ├── backtest.py      # Score backtest engine
│   └── sector_rotation.py # Sector rotation analysis (ETF-based)
├── fetchers/
│   ├── parqet.py        # Parqet Connect API (OAuth2 PKCE)
│   ├── parqet_auth.py   # Token management
│   ├── fmp.py           # Financial Modeling Prep
│   ├── yfinance_data.py # Yahoo Finance (batch, fundamentals, earnings surprise)
│   ├── yfinance_ws.py   # yFinance WebSocket (real-time, international)
│   ├── yfinance_screener.py # Stock discovery (EquityQuery)
│   ├── technical.py     # RSI, SMA, MACD
│   ├── fear_greed.py    # CNN Fear & Greed
│   ├── currency.py      # Exchange rates
│   └── demo_data.py     # Demo data
├── services/
│   ├── refresh.py       # Main refresh (with progress tracking)
│   ├── data_loader.py   # Parallel batch loading
│   ├── portfolio_builder.py # Parqet update + yFinance prices + portfolio totals
│   ├── ai_agent.py      # Daily AI Telegram report
│   ├── telegram.py      # Telegram API
│   ├── telegram_bot.py  # Telegram bot (command handler)
│   ├── vertex_ai.py     # Gemini client + context caching
│   ├── trade_advisor.py # AI Trade Advisor (Function Calling + Structured Output + Chat)
│   ├── earnings_ai.py   # Earnings analysis (Structured Output)
│   ├── score_commentary.py  # AI score commentaries (Structured Output)
│   ├── weekly_digest.py # Weekly digest (Flash)
│   ├── news_kurator.py  # Proactive portfolio news alerts (Structured Output)
│   ├── tech_radar_ai.py # Tech recommendations (AI)
│   ├── analyst_tracker.py   # Analyst track record
│   ├── knowledge_data.py    # Knowledge base (project facts + daily tips)
│   ├── url_fetcher.py       # URL content fetcher (HTML→Text for AI tools)
│   └── currency_converter.py
├── routes/
│   ├── portfolio.py     # Portfolio + dashboard
│   ├── refresh.py       # Refresh + status
│   ├── analysis.py      # Analysis reports
│   ├── analytics.py     # Extended analytics + attribution
│   ├── demo.py          # Demo mode toggle (activate/deactivate/status)
│   ├── parqet_oauth.py  # OAuth2 PKCE
│   ├── streaming.py     # SSE price stream
│   └── telegram.py      # Telegram webhook (with secret token)
├── static/
│   ├── index.html       # Dashboard UI
│   ├── app.js           # Frontend logic
│   └── styles.css       # Styling
└── tests/               # 368+ pytest tests (21 test files)
```
