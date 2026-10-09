"""跨重启持久化的系统级元数据。

目前只有一项：系统首次上线时间（first_started_at）。

管理后台的"系统运行时间"要显示累计值，而不是进程重启后的归零值。
首次启动时间写进宿主机文件（backend/data/system_meta.json，随 bind mount 持久），
之后每次进程启动都读同一个文件，容器重建也不会丢。

初始化只发生一次：由调用方给出一个 seed（如当前进程启动时间、库里最早业务时间），
取其中最早者写盘；文件一旦存在就不再改写，后续清库/重建容器都不影响已记录的起点。
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# app/core/system_meta.py -> app/core -> app -> backend/
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
META_FILE = _BACKEND_ROOT / "data" / "system_meta.json"

_first_started_at: Optional[datetime] = None


def get_first_started_at() -> Optional[datetime]:
    """返回已持久化的首次上线时间；尚未初始化时返回 None。"""
    global _first_started_at
    if _first_started_at is not None:
        return _first_started_at
    if not META_FILE.exists():
        return None
    try:
        raw = json.loads(META_FILE.read_text(encoding="utf-8"))
        value = datetime.fromisoformat(raw["first_started_at"])
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        _first_started_at = value
        return _first_started_at
    except (ValueError, KeyError, OSError):
        # 文件损坏：当作未初始化，由调用方重新 seed
        return None


def init_first_started_at(seed: datetime) -> datetime:
    """首次初始化并落盘。返回实际采用的值。

    幂等：文件已存在时直接返回已有值，不覆盖（避免晚启动的进程改写更早的起点）。
    """
    global _first_started_at
    existing = get_first_started_at()
    if existing is not None:
        return existing

    if seed.tzinfo is None:
        seed = seed.replace(tzinfo=timezone.utc)
    value = seed.astimezone(timezone.utc)
    # 不晚于当前时间才合理；出现未来时间（时钟回拨等）就退回当前时刻
    if value > datetime.now(timezone.utc):
        value = datetime.now(timezone.utc)

    META_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = META_FILE.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps({"first_started_at": value.isoformat()}, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, META_FILE)
    _first_started_at = value
    return value
