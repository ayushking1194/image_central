from datetime import datetime

from typing import Optional

from pydantic import BaseModel, ConfigDict


class ImageCreate(BaseModel):
    name: str
    version: str
    source: Optional[str] = None


class ImageRead(BaseModel):
    id: int
    name: str
    version: str
    sha256: str
    source: Optional[str]
    storage_uri: str
    approved: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PrismCentralCreate(BaseModel):
    name: str
    api_url: str
    username: Optional[str] = None
    password: Optional[str] = None


class PrismCentralRead(BaseModel):
    id: int
    name: str
    api_url: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SyncJobRead(BaseModel):
    id: int
    image_id: int
    pc_id: int
    status: str
    detail: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
