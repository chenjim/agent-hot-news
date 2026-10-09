from pathlib import Path
import os


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def _candidate_dirs():
    """按优先级返回 cookie 文件查找目录。

    cookie.*.txt 统一放在 backend/：
    - 容器内：随 ./backend:/app 挂载，/app/cookie.*.txt 命中
    - 宿主机：pytest/.bat 的 cwd 通常就是 backend/，cwd 命中
    - COOKIE_DIR 环境变量：显式覆盖，优先级最高
    - PROJECT_ROOT：历史遗留位置，兜底
    """
    dirs = [PROJECT_ROOT, Path("/app"), Path.cwd()]
    override = os.environ.get("COOKIE_DIR")
    if override:
        dirs.insert(0, Path(override))
    # 去重且只保留存在的目录
    seen = []
    for d in dirs:
        if d not in seen:
            seen.append(d)
    return [d for d in seen if d.is_dir()]


def load_cookie(name: str) -> str:
    """Load cookie value from cookie.<name>.txt (multi-dir search)."""
    filename = f"cookie.{name}.txt"
    for directory in _candidate_dirs():
        file_path = directory / filename
        if file_path.is_file():
            return file_path.read_text(encoding="utf-8").strip()
    return ""
