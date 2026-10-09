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
    OPENAI_EMBEDDING_MODEL: str = "qwen3-embedding:0.6b"
    
    # Local LLM fallback
    LOCAL_LLM_URL: str = "http://localhost:11434/api/generate"
    LOCAL_LLM_MODEL: str = "qwen2.5:14b"
    # App
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # API access tokens. Empty string = auth disabled (open access).
    #   READ_TOKEN  protects GET endpoints (hot-events / articles / sources / admin / sse)
    #   WRITE_TOKEN protects mutating endpoints (sources POST/PUT/DELETE, trigger-*)
    READ_TOKEN: str = ""
    WRITE_TOKEN: str = ""
    # CORS：逗号分隔，空则用内置默认；如 CORS_ORIGINS=https://news.h89.cn
    CORS_ORIGINS: str = ""
    # Fetch intervals (random range, minutes)
    FETCH_INTERVAL_DAY_MIN: int = 30
    FETCH_INTERVAL_DAY_MAX: int = 60
    FETCH_INTERVAL_NIGHT_MIN: int = 60
    FETCH_INTERVAL_NIGHT_MAX: int = 120

    # AI process interval (fixed, minutes)
    AI_PROCESS_INTERVAL_MINUTES: int = 15
    MAX_ARTICLES_PER_BATCH: int = 500
    EMBEDDING_DIMENSION: int = 1024

    # Data retention (days); older articles/events are cleaned up daily
    CLEANUP_RETENTION_DAYS: int = 5

    # ---- 聚合（归属判定）参数 ----
    # 事件匹配/硬合并的回看窗口（天）。与展示窗口一致，避免"看得见但合不上"。
    EVENT_MATCH_WINDOW_DAYS: int = 7
    # 归属判定的向量召回：每个待归类条目取最相似的前 K 个候选事件
    ROUTE_TOP_K: int = 3
    # 召回下限（余弦相似度）。低于此值直接判"新事件"，不进 LLM，
    # 省调用；取值必须低于同事件跨簇实测下限（0.468），只做召回闸门不做判定。
    ROUTE_RECALL_FLOOR: float = 0.35
    # 单次 LLM 归属判定最多处理多少条目
    ROUTE_BATCH_SIZE: int = 40
    # outlier 未被任何事件收编前最多重试几轮（C：待定池老化）
    ROUTE_MAX_ATTEMPTS: int = 3
    # 事件成立所需的最少来源数（按 source_name 计，即采集器一级）。
    # 同一来源的多条条目往往本就是不同话题（热榜/微博榜），聚一起是噪音；
    # 跨来源印证过的才算事件。设为 1 即关闭该规则、回到无条件聚合。
    MIN_EVENT_SOURCES: int = 2
    # 事件对外发布所需的文章数：不满 3 篇不上首页（aggregated_at 留空）。
    # 达标瞬间打点 aggregated_at，此后永不刷新 —— 展示时间与排序都用它。
    MIN_PUBLISH_ARTICLES: int = 3
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
