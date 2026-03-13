"""FinanzBro - AI Trade Advisor v2.

Evaluiert Kauf/Verkauf/Aufstocken-Entscheidungen mit:
  - Gemini 2.5 Pro (AI-Analyse + Google Search Grounding)
  - Function Calling: Gemini ruft selbst Score/Portfolio/Market-Tools auf
  - Structured Output: Garantiert valides JSON-Response
  - Optionale externe Quellen (Analysten, Artikel, User-Notizen)

v2 Änderungen:
  Feature 1: Structured Output (response_schema)
  Feature 2: Function Calling (Gemini entscheidet welche Daten benötigt werden)
"""
import json
import logging
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)


async def evaluate_trade(
    ticker: str,
    action: str = "buy",
    amount_eur: Optional[float] = None,
    extra_context: Optional[str] = None,
) -> dict:
    """Evaluiert eine Trade-Entscheidung mit AI + Function Calling.

    Args:
        ticker: Aktien-Ticker (z.B. "NVDA", "AAPL")
        action: "buy" (Neukauf), "sell" (Verkauf), "increase" (Aufstocken)
        amount_eur: Geplanter Betrag in EUR (optional)
        extra_context: Zusätzliche Informationen vom User (Analysten, Artikel)

    Returns:
        dict mit AI-Bewertung, Score, Portfolio-Impact, Risiken
    """
    from state import portfolio_data

    if not settings.gemini_configured:
        return {
            "error": "Gemini API nicht konfiguriert. Bitte GEMINI_API_KEY setzen.",
            "recommendation": "unknown",
        }

    summary = portfolio_data.get("summary")
    if not summary or not summary.stocks:
        return {
            "error": "Keine Portfolio-Daten vorhanden. Bitte zuerst einen Refresh starten.",
            "recommendation": "unknown",
        }

    ticker = ticker.upper().strip()
    action = action.lower().strip()
    if action not in ("buy", "sell", "increase"):
        action = "buy"

    # Feature 2: Pre-compute data that tools will return
    score_info = await _get_or_calculate_score(ticker, summary)
    portfolio_ctx = _build_portfolio_context(summary, ticker, action, amount_eur)

    try:
        result = await _call_gemini_with_tools(
            ticker=ticker,
            action=action,
            amount_eur=amount_eur,
            score_info=score_info,
            portfolio_ctx=portfolio_ctx,
            extra_context=extra_context,
        )
        result["ticker"] = ticker
        result["action"] = action
        result["amount_eur"] = amount_eur
        result["score"] = score_info
        result["portfolio_context"] = portfolio_ctx
        return result
    except Exception as e:
        logger.error(f"Trade Advisor Fehler: {e}")
        return {
            "error": str(e),
            "ticker": ticker,
            "action": action,
            "score": score_info,
            "portfolio_context": portfolio_ctx,
            "recommendation": "unknown",
        }


# ─────────────────────────────────────────────────────────────
# Score-Berechnung
# ─────────────────────────────────────────────────────────────

async def _get_or_calculate_score(ticker: str, summary) -> dict:
    """Holt Score aus Portfolio-Cache oder berechnet ihn live."""
    for stock in summary.stocks:
        if stock.position.ticker == ticker and stock.score:
            s = stock.score
            return {
                "total_score": s.total_score,
                "rating": s.rating.value,
                "confidence": s.confidence,
                "in_portfolio": True,
                "current_weight": round(
                    stock.position.current_value / summary.total_value * 100, 1
                ) if summary.total_value > 0 else 0,
                "current_pnl_pct": stock.position.pnl_percent,
                "breakdown": {
                    "quality": s.breakdown.quality_score,
                    "valuation": s.breakdown.valuation_score,
                    "analyst": s.breakdown.analyst_score,
                    "technical": s.breakdown.technical_score,
                    "momentum": s.breakdown.momentum_score,
                    "sentiment": s.breakdown.sentiment_score,
                },
            }

    # Nicht im Portfolio → Live-Score berechnen
    try:
        from services.data_loader import load_position_data
        from models import PortfolioPosition
        from fetchers.fear_greed import fetch_fear_greed_index

        fear_greed = summary.fear_greed
        if not fear_greed:
            try:
                fear_greed = await fetch_fear_greed_index()
            except Exception:
                pass

        dummy_pos = PortfolioPosition(
            ticker=ticker,
            name=ticker,
            shares=0,
            avg_cost=0,
            current_price=0,
        )
        stock_data = await load_position_data(dummy_pos, fear_greed)

        if stock_data.score:
            s = stock_data.score
            return {
                "total_score": s.total_score,
                "rating": s.rating.value,
                "confidence": s.confidence,
                "in_portfolio": False,
                "current_weight": 0,
                "current_pnl_pct": 0,
                "name": stock_data.position.name,
                "sector": stock_data.position.sector,
                "breakdown": {
                    "quality": s.breakdown.quality_score,
                    "valuation": s.breakdown.valuation_score,
                    "analyst": s.breakdown.analyst_score,
                    "technical": s.breakdown.technical_score,
                    "momentum": s.breakdown.momentum_score,
                    "sentiment": s.breakdown.sentiment_score,
                },
            }
    except Exception as e:
        logger.warning(f"Live-Score für {ticker} fehlgeschlagen: {e}")

    return {
        "total_score": None,
        "rating": "unknown",
        "in_portfolio": False,
        "confidence": 0,
        "current_weight": 0,
    }


# ─────────────────────────────────────────────────────────────
# Portfolio-Kontext
# ─────────────────────────────────────────────────────────────

def _build_portfolio_context(summary, ticker: str, action: str, amount_eur: Optional[float]) -> dict:
    """Baut Portfolio-Kontext für die AI-Analyse."""
    total = summary.total_value or 1
    stocks = [s for s in summary.stocks if s.position.ticker != "CASH"]

    sectors = {}
    for s in stocks:
        sec = s.position.sector or "Unknown"
        sectors[sec] = sectors.get(sec, 0) + s.position.current_value
    sector_pcts = {k: round(v / total * 100, 1) for k, v in sectors.items()}

    positions = []
    for s in sorted(stocks, key=lambda x: x.position.current_value, reverse=True)[:10]:
        positions.append({
            "ticker": s.position.ticker,
            "name": s.position.name,
            "weight": round(s.position.current_value / total * 100, 1),
            "score": s.score.total_score if s.score else None,
            "rating": s.score.rating.value if s.score else "unknown",
            "pnl_pct": s.position.pnl_percent,
            "sector": s.position.sector,
        })

    impact = {}
    if amount_eur and amount_eur > 0:
        target_ticker_sector = None
        for s in summary.stocks:
            if s.position.ticker == ticker:
                target_ticker_sector = s.position.sector
                break
        new_total = total + amount_eur if action != "sell" else total - amount_eur
        if new_total > 0 and target_ticker_sector:
            old_sector_pct = sector_pcts.get(target_ticker_sector, 0)
            sector_value = sectors.get(target_ticker_sector, 0)
            new_sector_value = sector_value - amount_eur if action == "sell" else sector_value + amount_eur
            new_sector_pct = round(new_sector_value / new_total * 100, 1)
            impact = {
                "sector": target_ticker_sector,
                "sector_weight_before": old_sector_pct,
                "sector_weight_after": new_sector_pct,
                "portfolio_value_after": round(new_total, 2),
            }

    return {
        "total_value": round(total, 2),
        "num_positions": len(stocks),
        "total_pnl_pct": summary.total_pnl_percent,
        "fear_greed": summary.fear_greed.value if summary.fear_greed else None,
        "fear_greed_label": summary.fear_greed.label if summary.fear_greed else None,
        "sector_distribution": sector_pcts,
        "top_positions": positions,
        "impact": impact,
    }


# ─────────────────────────────────────────────────────────────
# Feature 2: Function Calling — Tool Definitionen
# ─────────────────────────────────────────────────────────────

def _build_tool_declarations() -> list[dict]:
    """Definiert die Tools die Gemini aufrufen kann."""
    return [
        {
            "name": "get_stock_score",
            "description": (
                "Berechnet den 10-Faktor-Score einer Aktie. "
                "Gibt Score (0-100), Rating (buy/hold/sell), Confidence und Score-Breakdown zurück."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Aktien-Ticker (z.B. NVDA, AAPL)",
                    },
                },
                "required": ["ticker"],
            },
        },
        {
            "name": "get_portfolio_overview",
            "description": (
                "Gibt eine Übersicht des aktuellen Portfolios: Gesamtwert, Positionen, "
                "Sektor-Verteilung, P&L, Fear&Greed Index."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
        {
            "name": "get_sector_impact",
            "description": (
                "Simuliert den Impact eines Trades auf die Sektor-Verteilung des Portfolios."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "action": {"type": "string", "enum": ["buy", "sell", "increase"]},
                    "amount_eur": {"type": "number"},
                },
                "required": ["ticker", "action", "amount_eur"],
            },
        },
    ]


def _execute_tool_call(
    tool_name: str,
    tool_args: dict,
    score_info: dict,
    portfolio_ctx: dict,
) -> str:
    """Führt einen Tool-Aufruf aus und gibt das Ergebnis als JSON-String zurück."""
    if tool_name == "get_stock_score":
        return json.dumps(score_info, default=str)

    elif tool_name == "get_portfolio_overview":
        # Slim version: nur die wichtigsten Felder
        overview = {
            "total_value": portfolio_ctx["total_value"],
            "num_positions": portfolio_ctx["num_positions"],
            "total_pnl_pct": portfolio_ctx["total_pnl_pct"],
            "fear_greed": portfolio_ctx.get("fear_greed"),
            "fear_greed_label": portfolio_ctx.get("fear_greed_label"),
            "sector_distribution": portfolio_ctx["sector_distribution"],
            "top_positions": portfolio_ctx["top_positions"][:5],
        }
        return json.dumps(overview, default=str)

    elif tool_name == "get_sector_impact":
        impact = portfolio_ctx.get("impact", {})
        if not impact:
            return json.dumps({"info": "Keine Impact-Daten verfügbar (Betrag oder Sektor fehlt)"})
        return json.dumps(impact, default=str)

    return json.dumps({"error": f"Unbekanntes Tool: {tool_name}"})


# ─────────────────────────────────────────────────────────────
# Feature 1: Structured Output Schema
# ─────────────────────────────────────────────────────────────

ADVISOR_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "recommendation": {
            "type": "string",
            "enum": ["buy", "hold", "reduce", "avoid"],
            "description": "Trade-Empfehlung",
        },
        "confidence": {
            "type": "integer",
            "description": "Confidence 0-100",
        },
        "summary": {
            "type": "string",
            "description": "1-2 Sätze Fazit auf Deutsch",
        },
        "bull_case": {
            "type": "string",
            "description": "Argumente für den Trade",
        },
        "bear_case": {
            "type": "string",
            "description": "Argumente gegen den Trade",
        },
        "portfolio_fit": {
            "type": "string",
            "description": "Wie passt der Trade zum Portfolio?",
        },
        "sizing_advice": {
            "type": "string",
            "description": "Empfohlene Positionsgröße",
        },
        "risks": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Liste der wichtigsten Risiken",
        },
        "timing": {
            "type": "string",
            "description": "Timing-Einschätzung",
        },
        "external_analysis": {
            "type": "string",
            "description": "Zusammenfassung externer Quellen",
        },
    },
    "required": ["recommendation", "confidence", "summary", "bull_case",
                 "bear_case", "portfolio_fit", "sizing_advice", "risks", "timing"],
}


# ─────────────────────────────────────────────────────────────
# Gemini API Call mit Function Calling + Structured Output
# ─────────────────────────────────────────────────────────────

async def _call_gemini_with_tools(
    ticker: str,
    action: str,
    amount_eur: Optional[float],
    score_info: dict,
    portfolio_ctx: dict,
    extra_context: Optional[str],
) -> dict:
    """Ruft Gemini 2.5 Pro mit Function Calling + Structured Output auf.

    Flow:
    1. Sende Prompt + Tool-Definitionen an Gemini
    2. Gemini entscheidet welche Tools es braucht
    3. Wir führen die Tools aus und senden Ergebnisse zurück
    4. Gemini erstellt die finale Bewertung (Structured Output)
    """
    from services.vertex_ai import get_client, get_cached_content
    from google.genai.types import Tool, GoogleSearch, FunctionDeclaration, Part, Content

    client = get_client()

    # System-Prompt
    action_de = {"buy": "Kauf", "sell": "Verkauf", "increase": "Aufstocken"}.get(action, action)
    system_prompt = (
        "Du bist ein erfahrener Portfolio-Advisor. Der User möchte einen Trade evaluieren. "
        "Du hast Zugriff auf Tools um Portfolio-Daten und Aktien-Scores abzurufen. "
        "Nutze die Tools um deine Analyse zu untermauern. "
        "Nutze auch Google Search für aktuelle Marktdaten und Nachrichten. "
        "Antworte auf Deutsch."
    )

    # User-Prompt
    user_prompt_parts = [
        f"Evaluiere folgenden Trade: {action_de.upper()} von {ticker}",
    ]
    if amount_eur:
        user_prompt_parts.append(f"Geplanter Betrag: {amount_eur:,.0f} EUR")
    if extra_context:
        user_prompt_parts.append(f"\nExterne Quellen vom User:\n{extra_context.strip()[:3000]}")
    user_prompt_parts.append(
        "\nNutze die verfügbaren Tools um den Score und das Portfolio abzufragen, "
        "dann erstelle eine professionelle Trade-Bewertung."
    )
    user_prompt = "\n".join(user_prompt_parts)

    # Tool-Definitionen
    tool_declarations = [
        FunctionDeclaration(**td) for td in _build_tool_declarations()
    ]

    # Config: Google Search + eigene Tools
    config = {
        "tools": [
            Tool(google_search=GoogleSearch()),
            Tool(function_declarations=tool_declarations),
        ],
        "response_mime_type": "application/json",
        "response_schema": ADVISOR_RESPONSE_SCHEMA,
        "system_instruction": system_prompt,
    }

    cached = get_cached_content()
    if cached:
        config["cached_content"] = cached

    # Schritt 1: Initiale Anfrage
    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=user_prompt,
        config=config,
    )

    # Schritt 2: Function Calling Loop (max 3 Runden)
    contents = [
        Content(role="user", parts=[Part(text=user_prompt)]),
        response.candidates[0].content,
    ]

    for round_num in range(3):
        # Prüfe ob Gemini Tools aufrufen will
        function_calls = []
        for part in response.candidates[0].content.parts:
            if part.function_call:
                function_calls.append(part)

        if not function_calls:
            break  # Gemini ist fertig → finale Antwort

        logger.info(f"🔧 Function Calling Runde {round_num + 1}: "
                     f"{len(function_calls)} Tool-Aufrufe")

        # Alle Tool-Aufrufe ausführen
        tool_results = []
        for fc_part in function_calls:
            fc = fc_part.function_call
            tool_name = fc.name
            tool_args = dict(fc.args) if fc.args else {}

            logger.debug(f"  Tool: {tool_name}({tool_args})")
            result_str = _execute_tool_call(
                tool_name, tool_args, score_info, portfolio_ctx,
            )

            tool_results.append(Part.from_function_response(
                name=tool_name,
                response={"result": result_str},
            ))

        # Tool-Ergebnisse zurücksenden
        contents.append(Content(role="user", parts=tool_results))

        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=contents,
            config=config,
        )
        contents.append(response.candidates[0].content)

    # Finale Antwort parsen
    raw = response.text.strip() if response.text else ""
    logger.info(f"🧠 Trade Advisor Response ({len(raw)} Zeichen, "
                f"nach {round_num + 1 if function_calls else 0} Tool-Runden)")

    return _parse_ai_response(raw)


def _parse_ai_response(raw: str) -> dict:
    """Parsed die Gemini-Antwort zu strukturiertem Dict.

    Mit Structured Output (Feature 1) sollte dies immer valides JSON sein.
    Fallback für Edge-Cases wird beibehalten.
    """
    cleaned = raw
    if "```json" in cleaned:
        cleaned = cleaned.split("```json", 1)[1]
    if "```" in cleaned:
        cleaned = cleaned.split("```", 1)[0]
    cleaned = cleaned.strip()

    try:
        result = json.loads(cleaned)
        defaults = {
            "recommendation": "hold",
            "confidence": 50,
            "summary": "",
            "bull_case": "",
            "bear_case": "",
            "portfolio_fit": "",
            "sizing_advice": "",
            "risks": [],
            "timing": "",
            "external_analysis": "",
        }
        for key, default in defaults.items():
            if key not in result:
                result[key] = default
        return result
    except json.JSONDecodeError:
        logger.warning(f"JSON-Parsing fehlgeschlagen, verwende Freitext")
        return {
            "recommendation": "hold",
            "confidence": 50,
            "summary": raw[:500],
            "bull_case": "",
            "bear_case": "",
            "portfolio_fit": "",
            "sizing_advice": "",
            "risks": [],
            "timing": "",
            "external_analysis": "",
            "raw_response": raw,
        }


# ─────────────────────────────────────────────────────────────
# Chat Advisor — Freie Konversation mit Portfolio-Kontext
# ─────────────────────────────────────────────────────────────

async def chat_with_advisor(
    message: str,
    history: list[dict] | None = None,
) -> dict:
    """Freie Konversation mit dem AI Advisor.

    Unterstützt beliebige Fragen/Hypothesen mit Portfolio-Kontext.
    Nutzt Function Calling für Live-Daten und Google Search für Aktualität.

    Args:
        message: Aktuelle Nachricht des Users
        history: Bisheriger Chat-Verlauf [{"role": "user"|"assistant", "content": "..."}]

    Returns:
        dict mit "response" (AI-Antwort), "history" (aktualisiert)
    """
    from state import portfolio_data

    if not settings.gemini_configured:
        return {
            "response": "⚠️ Gemini API nicht konfiguriert. Bitte GEMINI_API_KEY setzen.",
            "history": history or [],
        }

    summary = portfolio_data.get("summary")
    if not summary or not summary.stocks:
        return {
            "response": "⚠️ Keine Portfolio-Daten vorhanden. Bitte zuerst einen Refresh starten.",
            "history": history or [],
        }

    if not message or not message.strip():
        return {
            "response": "Bitte stelle eine Frage oder beschreibe deine Hypothese.",
            "history": history or [],
        }

    # Portfolio-Kontext für System-Prompt aufbauen
    portfolio_ctx = _build_portfolio_context(summary, "", "buy", None)

    # Score-Info für Tool-Calls (leerer Dummy — wird live berechnet)
    score_info = {"info": "Nutze get_stock_score Tool für Ticker-spezifische Scores"}

    try:
        response_text = await _call_gemini_chat(
            message=message.strip(),
            history=history or [],
            portfolio_ctx=portfolio_ctx,
            score_info=score_info,
            summary=summary,
        )
        # History aktualisieren
        updated_history = list(history or [])
        updated_history.append({"role": "user", "content": message.strip()})
        updated_history.append({"role": "assistant", "content": response_text})

        # History auf max 20 Nachrichten begrenzen (10 Turns)
        if len(updated_history) > 20:
            updated_history = updated_history[-20:]

        return {
            "response": response_text,
            "history": updated_history,
        }
    except Exception as e:
        logger.error(f"Chat Advisor Fehler: {e}")
        return {
            "response": f"❌ Fehler bei der AI-Analyse: {str(e)}",
            "history": history or [],
        }


async def _call_gemini_chat(
    message: str,
    history: list[dict],
    portfolio_ctx: dict,
    score_info: dict,
    summary,
) -> str:
    """Gemini-Call für freie Chat-Konversation mit Function Calling."""
    from services.vertex_ai import get_client, get_cached_content
    from google.genai.types import Tool, GoogleSearch, FunctionDeclaration, Part, Content

    client = get_client()

    # Portfolio-Zusammenfassung für System-Prompt
    positions_text = ""
    for p in portfolio_ctx.get("top_positions", [])[:15]:
        positions_text += (
            f"  {p['ticker']} ({p['name']}): "
            f"Gewicht {p['weight']}%, Score {p.get('score', '?')}, "
            f"Rating {p.get('rating', '?')}, P&L {p.get('pnl_pct', 0):.1f}%\n"
        )

    sectors_text = ", ".join(
        f"{k} {v}%" for k, v in portfolio_ctx.get("sector_distribution", {}).items()
    )

    system_prompt = (
        "Du bist ein erfahrener Portfolio-Berater und Finanzanalyst. "
        "Der User hat ein persönliches Aktienportfolio und möchte mit dir darüber diskutieren.\n\n"
        f"PORTFOLIO-ÜBERSICHT:\n"
        f"  Gesamtwert: {portfolio_ctx.get('total_value', 0):,.0f} EUR\n"
        f"  Positionen: {portfolio_ctx.get('num_positions', 0)}\n"
        f"  Gesamt P&L: {portfolio_ctx.get('total_pnl_pct', 0):.1f}%\n"
        f"  Fear & Greed: {portfolio_ctx.get('fear_greed', '?')} ({portfolio_ctx.get('fear_greed_label', '?')})\n"
        f"  Sektor-Verteilung: {sectors_text}\n\n"
        f"POSITIONEN:\n{positions_text}\n"
        "REGELN:\n"
        "- Antworte auf Deutsch, klar und direkt\n"
        "- Nutze die verfügbaren Tools um aktuelle Daten abzurufen wenn nötig\n"
        "- Nutze Google Search für aktuelle Nachrichten und Marktdaten\n"
        "- Beziehe dich auf das Portfolio wenn relevant\n"
        "- Sei ehrlich über Unsicherheiten und Risiken\n"
        "- Formatiere mit Markdown (fett, Listen, Überschriften)\n"
    )

    # Tool-Definitionen (gleiche wie bei evaluate)
    tool_declarations = [
        FunctionDeclaration(**td) for td in _build_tool_declarations()
    ]

    config = {
        "tools": [
            Tool(function_declarations=tool_declarations),
        ],
        "system_instruction": system_prompt,
    }

    cached = get_cached_content()
    if cached:
        config["cached_content"] = cached

    # Chat-History als Contents aufbauen
    contents = []
    for msg in history:
        role = "user" if msg["role"] == "user" else "model"
        contents.append(Content(role=role, parts=[Part(text=msg["content"])]))

    # Aktuelle Nachricht hinzufügen
    contents.append(Content(role="user", parts=[Part(text=message)]))

    # Gemini-Call
    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=contents,
        config=config,
    )

    # Function Calling Loop (max 3 Runden)
    all_contents = list(contents)
    all_contents.append(response.candidates[0].content)

    for round_num in range(3):
        function_calls = [
            p for p in response.candidates[0].content.parts
            if p.function_call
        ]
        if not function_calls:
            break

        logger.info(f"💬 Chat Tool-Runde {round_num + 1}: {len(function_calls)} Calls")

        # Tool-Calls ausführen
        tool_results = []
        for fc_part in function_calls:
            fc = fc_part.function_call
            tool_name = fc.name
            tool_args = dict(fc.args) if fc.args else {}

            # Für get_stock_score: Live-Score berechnen
            if tool_name == "get_stock_score":
                ticker = tool_args.get("ticker", "")
                live_score = await _get_or_calculate_score(ticker, summary)
                result_str = json.dumps(live_score, default=str)
            else:
                result_str = _execute_tool_call(
                    tool_name, tool_args, score_info, portfolio_ctx,
                )

            tool_results.append(Part.from_function_response(
                name=tool_name,
                response={"result": result_str},
            ))

        all_contents.append(Content(role="user", parts=tool_results))

        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=all_contents,
            config=config,
        )
        all_contents.append(response.candidates[0].content)

    return response.text.strip() if response.text else "Keine Antwort erhalten."

