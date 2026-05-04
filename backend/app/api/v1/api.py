from fastapi import APIRouter
from app.api.v1.endpoints import hot_events, sources, articles, sse, admin

api_router = APIRouter()

api_router.include_router(hot_events.router, prefix="/hot-events", tags=["hot-events"])
api_router.include_router(sources.router, prefix="/sources", tags=["sources"])
api_router.include_router(articles.router, prefix="/articles", tags=["articles"])
api_router.include_router(sse.router, prefix="/sse", tags=["sse"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
