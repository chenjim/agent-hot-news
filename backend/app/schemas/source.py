from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict, Any
from app.models.models import SourceType, SourceStatus


class SourceBase(BaseModel):
    name: str
    type: SourceType = SourceType.RSS
    endpoint: str
    config: Optional[Dict[str, Any]] = {}

    model_config = {"populate_by_name": True}


class SourceCreate(SourceBase):
    pass


class SourceRead(SourceBase):
    id: int
    status: SourceStatus
    last_fetched_at: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SourceUpdate(BaseModel):
    name: Optional[str] = None
    endpoint: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    status: Optional[SourceStatus] = None

    model_config = {"populate_by_name": True}
