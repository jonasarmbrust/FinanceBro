"""FinanceBro - Simple In-Memory Rate Limiter.

Schützt teure AI-Endpoints (Gemini API) vor exzessiven Aufrufen.
Verwendet ein Token-Bucket-Muster pro Endpoint.
"""
import time
import logging
from collections import defaultdict
from functools import wraps

from fastapi import HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# Bucket: {endpoint: {window_start: float, count: int}}
_rate_buckets: dict[str, dict] = defaultdict(lambda: {"window_start": 0.0, "count": 0})

# Konfiguration: max Aufrufe pro Zeitfenster
RATE_LIMITS = {
    "advisor_evaluate": {"max_calls": 10, "window_seconds": 60},
    "advisor_chat": {"max_calls": 15, "window_seconds": 60},
    "shadow_run": {"max_calls": 3, "window_seconds": 300},
    "shadow_reset": {"max_calls": 2, "window_seconds": 600},
    "default": {"max_calls": 30, "window_seconds": 60},
}


def check_rate_limit(endpoint: str) -> bool:
    """Prüft ob ein Endpoint-Aufruf erlaubt ist.

    Returns True wenn erlaubt, wirft HTTPException 429 wenn limitiert.
    """
    config = RATE_LIMITS.get(endpoint, RATE_LIMITS["default"])
    bucket = _rate_buckets[endpoint]
    now = time.monotonic()

    # Fenster abgelaufen → Reset
    if now - bucket["window_start"] > config["window_seconds"]:
        bucket["window_start"] = now
        bucket["count"] = 0

    bucket["count"] += 1

    if bucket["count"] > config["max_calls"]:
        window = config["window_seconds"]
        logger.warning(f"Rate limit erreicht: {endpoint} ({bucket['count']}/{config['max_calls']} in {window}s)")
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit: max {config['max_calls']} Aufrufe pro {window}s. Bitte warten.",
        )

    return True
