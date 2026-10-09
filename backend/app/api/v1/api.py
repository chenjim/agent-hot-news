from fastapi import APIRouter, Depends

from app.api.v1.endpoints import hot_events, sources, articles, sse, admin
from app.core.auth import require_read

api_router = APIRouter()

# Pure-read routers: the whole router is guarded by the read token.
api_router.include_router(
    hot_events.router,
    prefix="/hot-events",
    tags=["hot-events"],
    dependencies=[Depends(require_read)],
)
api_router.include_router(
    articles.router,
    prefix="/articles",
    tags=["articles"],
    dependencies=[Depends(require_read)],
)
api_router.include_router(
    sse.router,
    prefix="/sse",
    tags=["sse"],
    dependencies=[Depends(require_read)],
)

# Mixed routers: each route declares its own guard (read token vs write token).
api_router.include_router(sources.router, prefix="/sources", tags=["sources"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
