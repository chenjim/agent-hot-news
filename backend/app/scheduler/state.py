from datetime import datetime, timezone
from typing import Optional

# Shared state between scheduler tasks and admin endpoints
_last_fetch_time: Optional[datetime] = None
_last_ai_time: Optional[datetime] = None

FETCH_COOLDOWN_SECONDS = 300  # 5 minutes
AI_COOLDOWN_SECONDS = 300     # 5 minutes


def get_last_fetch_time() -> Optional[datetime]:
    return _last_fetch_time


def set_last_fetch_time(time: Optional[datetime] = None):
    global _last_fetch_time
    _last_fetch_time = time or datetime.now(timezone.utc)


def get_last_ai_time() -> Optional[datetime]:
    return _last_ai_time


def set_last_ai_time(time: Optional[datetime] = None):
    global _last_ai_time
    _last_ai_time = time or datetime.now(timezone.utc)


def is_fetch_in_cooldown() -> bool:
    if _last_fetch_time is None:
        return False
    return (datetime.now(timezone.utc) - _last_fetch_time).total_seconds() < FETCH_COOLDOWN_SECONDS


def is_ai_in_cooldown() -> bool:
    if _last_ai_time is None:
        return False
    return (datetime.now(timezone.utc) - _last_ai_time).total_seconds() < AI_COOLDOWN_SECONDS