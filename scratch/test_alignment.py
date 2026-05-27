import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

# Setup simple logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_alignment")

# Add parent path to import config and fetchers
import sys
sys.path.append(str(Path(".").resolve()))

from config import settings
from fetchers.parqet import _ensure_valid_token, PARQET_CONNECT_API
import httpx

async def _fetch_parqet_milestones() -> list[tuple[str, float]]:
    access_token = await _ensure_valid_token()
    if not access_token or not settings.PARQET_PORTFOLIO_ID:
        logger.error("No token or portfolio ID")
        return []
        
    intervals = ["1d", "1w", "1m", "3m", "6m", "ytd", "1y"]
    milestones = []
    
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"{PARQET_CONNECT_API}/performance"
    
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r_today = await client.post(
                url, 
                json={"portfolioIds": [settings.PARQET_PORTFOLIO_ID], "interval": {"type": "relative", "value": "1d"}},
                headers=headers
            )
            if r_today.status_code == 200:
                data = r_today.json()
                today_str = data.get("interval", {}).get("end")
                today_val = data.get("performance", {}).get("valuation", {}).get("atIntervalEnd", 0)
                if today_str and today_val > 0:
                    milestones.append((today_str, today_val))
                    
            for val in intervals:
                resp = await client.post(
                    url,
                    json={"portfolioIds": [settings.PARQET_PORTFOLIO_ID], "interval": {"type": "relative", "value": val}},
                    headers=headers
                )
                if resp.status_code == 200:
                    data = resp.json()
                    start_date = data.get("interval", {}).get("start")
                    start_val = data.get("performance", {}).get("valuation", {}).get("atIntervalStart", 0)
                    if start_date and start_val > 0:
                        milestones.append((start_date, start_val))
    except Exception as e:
        logger.warning(f"Error loading Parqet milestones: {e}")
        
    unique_milestones = {}
    for date_str, val in milestones:
        unique_milestones[date_str] = val
        
    return sorted(unique_milestones.items())

async def align_snapshots_with_parqet(snapshots: list[dict]) -> list[dict]:
    milestones = await _fetch_parqet_milestones()
    if not milestones or not snapshots:
        return snapshots
        
    snap_map = {s["date"]: s["total_value"] for s in snapshots}
    milestone_offsets = []
    
    for m_date, m_val in milestones:
        rec_val = snap_map.get(m_date)
        if not rec_val:
            dates_in_snap = sorted(snap_map.keys())
            if not dates_in_snap:
                continue
            nearest_date = min(dates_in_snap, key=lambda x: abs((datetime.strptime(x, "%Y-%m-%d") - datetime.strptime(m_date, "%Y-%m-%d")).days))
            rec_val = snap_map[nearest_date]
        
        offset = m_val - rec_val
        milestone_offsets.append((m_date, offset))
        
    if not milestone_offsets:
        return snapshots
        
    milestone_offsets.sort(key=lambda x: x[0])
    logger.info(f"Milestone Offsets: {milestone_offsets}")
    
    adjusted_snapshots = []
    
    for s in snapshots:
        s_date = s["date"]
        s_val = s["total_value"]
        
        prev_m = None
        next_m = None
        
        for m_date, offset in milestone_offsets:
            if m_date <= s_date:
                prev_m = (m_date, offset)
            if m_date >= s_date and next_m is None:
                next_m = (m_date, offset)
                
        if prev_m is None:
            applied_offset = milestone_offsets[0][1]
        elif next_m is None:
            applied_offset = milestone_offsets[-1][1]
        elif prev_m[0] == next_m[0]:
            applied_offset = prev_m[1]
        else:
            d_prev = datetime.strptime(prev_m[0], "%Y-%m-%d")
            d_next = datetime.strptime(next_m[0], "%Y-%m-%d")
            d_curr = datetime.strptime(s_date, "%Y-%m-%d")
            
            total_days = (d_next - d_prev).days
            if total_days > 0:
                fraction = (d_curr - d_prev).days / total_days
                applied_offset = prev_m[1] + fraction * (next_m[1] - prev_m[1])
            else:
                applied_offset = prev_m[1]
                
        adjusted_val = round(s_val + applied_offset, 2)
        adjusted_snapshots.append({
            "date": s_date,
            "total_value": adjusted_val
        })
        
    return adjusted_snapshots

async def main():
    history_file = Path("cache/portfolio_history.json")
    if not history_file.exists():
        logger.error("No history file found")
        return
        
    data = json.loads(history_file.read_text(encoding="utf-8"))
    snapshots = data["daily"]
    
    adjusted = await align_snapshots_with_parqet(snapshots)
    
    # Calculate old and new YTD
    def calc_ytd(snaps):
        year_start = "2026-01-01"
        jan_entry = None
        for entry in snaps:
            if entry["date"] >= year_start:
                jan_entry = entry
                break
        if not jan_entry:
            return None
        start = jan_entry["total_value"]
        end = snaps[-1]["total_value"]
        return round(((end - start) / start) * 100, 2)
        
    print("Old YTD:", calc_ytd(snapshots))
    print("New YTD:", calc_ytd(adjusted))
    print("Old latest:", snapshots[-1])
    print("New latest:", adjusted[-1])

if __name__ == "__main__":
    asyncio.run(main())
