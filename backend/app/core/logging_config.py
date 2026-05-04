import sys
from pathlib import Path
from loguru import logger
from app.core.config import get_settings

settings = get_settings()

# Log directory: backend/logs/
LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Remove default stderr handler to avoid duplicates on re-import
logger.remove()

# Console output
logger.add(sys.stderr, level=settings.LOG_LEVEL)

# File output: daily rotation, keep 14 days
logger.add(
    LOG_DIR / "app_{time:YYYY-MM-DD}.log",
    rotation="1 day",
    retention="14 days",
    level=settings.LOG_LEVEL,
    encoding="utf-8",
)
