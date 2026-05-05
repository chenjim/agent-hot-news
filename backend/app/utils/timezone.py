from datetime import tzinfo
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@lru_cache(maxsize=16)
def get_tz(tz_name: str | None) -> tzinfo:
    """将时区名转为 ZoneInfo，非法时区回退到 Asia/Shanghai"""
    if not tz_name:
        return ZoneInfo("Asia/Shanghai")
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, KeyError):
        return ZoneInfo("Asia/Shanghai")
