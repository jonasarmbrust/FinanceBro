"""Test TipRanks MCP via the actual fetcher module."""
import asyncio
import os, sys
os.environ["PYTHONUTF8"] = "1"

from dotenv import load_dotenv
load_dotenv()

async def test():
    from config import settings
    print(f"API Key configured: {settings.tipranks_configured}")
    print(f"API Key: ***{settings.TIPRANKS_API_KEY[-6:]}")
    
    from fetchers.tipranks import fetch_tipranks_data, reset_session
    
    # Reset session to test fresh
    reset_session()
    
    print("\n=== Testing AAPL ===")
    result = await fetch_tipranks_data("AAPL")
    
    if result:
        print(f"  Smart Score: {result.smart_score}/10")
        print(f"  Analyst Consensus: {result.analyst_consensus}")
        print(f"  Analyst Count: {result.analyst_count}")
        print(f"  Buy/Hold/Sell: {result.buy_count}/{result.hold_count}/{result.sell_count}")
        print(f"  Price Target Avg: ${result.price_target_avg:.2f}")
        print(f"  Upside: {result.upside_potential:.1f}%")
        print(f"  Hedge Fund Trend: {result.hedge_fund_trend}")
        print(f"  Insider Trend: {result.insider_trend}")
        print(f"  News Sentiment: {result.news_sentiment}")
        print(f"  Bull Points: {len(result.bull_points)}")
        print(f"  Bear Points: {len(result.bear_points)}")
        print(f"  Risk Warnings: {len(result.risk_warnings)}")
        if result.bull_points:
            print(f"    Bull[0]: {result.bull_points[0][:80]}")
        if result.bear_points:
            print(f"    Bear[0]: {result.bear_points[0][:80]}")
        print("\nSUCCESS!")
    else:
        print("  FAILED — No data returned")
        print("  Check logs above for error details")

asyncio.run(test())
