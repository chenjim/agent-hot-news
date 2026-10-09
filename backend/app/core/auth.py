"""Read/write API token guards.

Token resolution order (first non-empty wins):
  1. dedicated header:  X-Read-Token / X-Write-Token
  2. Authorization: *** token>
  3. query parameter:   ?token=<token>   (EventSource cannot send headers)

An empty setting (READ_TOKEN/WRITE_TOKEN == "") disables the guard entirely,
which keeps local development unblocked. Comparison is timing-safe.
"""

import hmac
from typing import Optional

from fastapi import Header, HTTPException, Query

from app.core.config import get_settings

_UNAUTHORIZED = "Missing or invalid access token"


def _extract(
    dedicated: Optional[str],
    authorization: Optional[str],
    query_token: Optional[str],
) -> Optional[str]:
    if dedicated:
        return dedicated.strip()
    if authorization:
        parts = authorization.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()
        return authorization.strip()
    if query_token:
        return query_token.strip()
    return None


def _verify(expected: str, provided: Optional[str]) -> bool:
    if not expected:
        return True  # auth disabled
    if not provided:
        return False
    return hmac.compare_digest(expected, provided)


async def require_read(
    x_read_token: Optional[str] = Header(default=None, alias="X-Read-Token"),
    authorization: Optional[str] = Header(default=None),
    token: Optional[str] = Query(default=None),
) -> None:
    settings = get_settings()
    if not _verify(settings.READ_TOKEN, _extract(x_read_token, authorization, token)):
        raise HTTPException(status_code=401, detail=_UNAUTHORIZED)


async def require_write(
    x_write_token: Optional[str] = Header(default=None, alias="X-Write-Token"),
    authorization: Optional[str] = Header(default=None),
) -> None:
    settings = get_settings()
    if not _verify(settings.WRITE_TOKEN, _extract(x_write_token, authorization, None)):
        raise HTTPException(status_code=401, detail=_UNAUTHORIZED)
