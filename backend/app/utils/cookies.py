from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def load_cookie(name: str) -> str:
    """Load cookie value from cookie.<name>.txt in project root."""
    file_path = PROJECT_ROOT / f"cookie.{name}.txt"
    if not file_path.exists():
        return ""
    return file_path.read_text(encoding="utf-8").strip()
