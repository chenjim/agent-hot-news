import os
import uuid
from pathlib import Path
from pydantic_settings import BaseSettings
from functools import lru_cache
# Resolve .env file path: backend/app/core/ -> backend/ -> project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_ENV_FILE_PATH = _PROJECT_ROOT / ".env"
class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+psycopg2://hotnews:hotnews@localhost:51132/hotnews"
    REDIS_URL: str = "redis://localhost:51179/0"
    # Tianapi
    TIANAPI_KEY: str = ""

    # Weibo
    # Cookie moved to cookie.weibo.txt

    # Baidu
    # Cookie moved to cookie.baidu.txt

    # Zhihu
    # Cookie moved to cookie.zhihu.txt

    # Toutiao
    # Cookie moved to cookie.toutiao.txt

    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_CHAT_MODEL: str = "deepseek/deepseek-v4-flash"

    OPENAI_EMBEDDING_API_KEY: str = ""  # empty = fallback to OPENAI_API_KEY
    OPENAI_EMBEDDING_BASE_URL: str = ""  # empty = fallback to OPENAI_BASE_URL
    OPENAI_EMBEDDING_MODEL: str = "qwen/qwen3-embedding-8b"
    
    # Local LLM fallback
    LOCAL_LLM_URL: str = "http://localhost:11434/api/generate"
    LOCAL_LLM_MODEL: str = "qwen2.5:14b"
    # App
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    # CORS：逗号分隔，空则用内置默认；如 CORS_ORIGINS=https://f.h89.cn:51130
    CORS_ORIGINS: str = ""
    # Fetch intervals (random range, minutes)
    FETCH_INTERVAL_DAY_MIN: int = 30
    FETCH_INTERVAL_DAY_MAX: int = 60
    FETCH_INTERVAL_NIGHT_MIN: int = 60
    FETCH_INTERVAL_NIGHT_MAX: int = 120

    # AI process interval (fixed, minutes)
    AI_PROCESS_INTERVAL_MINUTES: int = 15
    MAX_ARTICLES_PER_BATCH: int = 500
    EMBEDDING_DIMENSION: int = 4096
    class Config:
        env_file = str(_ENV_FILE_PATH) if _ENV_FILE_PATH.exists() else ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"
@lru_cache()
def get_settings() -> Settings:
    s = Settings()
    # Debug print to verify config loading
    return s


# OpenCode Go 要求：base_url 含 opencode.ai 时携带 x-opencode-session（进程内稳定，用于服务端优化）
OPENCODE_SESSION_ID = os.environ.get("OPENCODE_SESSION_ID") or f"agent-hot-news-{uuid.uuid4()}"


def is_opencode_endpoint(base_url: str) -> bool:
    return "opencode.ai" in base_url


def llm_extra_headers(base_url: str) -> dict:
    if not is_opencode_endpoint(base_url):
        return {}
    return {"x-opencode-session": OPENCODE_SESSION_ID}
