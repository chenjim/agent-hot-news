from app.core import logging_config  # noqa: F401  # configures loguru handlers

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio

from app.database import engine, Base
from app.api.v1.api import api_router
from app.core.config import get_settings
from app.scheduler.tasks import start_scheduler, stop_scheduler
from app.seed import seed_sources

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    await asyncio.to_thread(Base.metadata.create_all, bind=engine)
    await asyncio.to_thread(seed_sources, engine)
    start_scheduler()
    yield
    # shutdown
    stop_scheduler()


app = FastAPI(
    title="Agent Hot News API",
    description="AI-driven multi-source hot news detection and aggregation",
    version="0.1.0",
    lifespan=lifespan,
)


def _cors_origins() -> list:
    if settings.CORS_ORIGINS.strip():
        return [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
    origins = ["http://localhost:51131", "https://f.h89.cn:51130"]
    if settings.DEBUG:
        origins.append("http://127.0.0.1:51131")
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
def health_check():
    return {"status": "ok"}
