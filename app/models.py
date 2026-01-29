from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db import Base


class Image(Base):
    __tablename__ = "images"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), index=True, nullable=False)
    version = Column(String(64), nullable=False)
    sha256 = Column(String(64), nullable=False)
    source = Column(String(255), nullable=True)
    storage_uri = Column(Text, nullable=False)
    approved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    sync_jobs = relationship(
        "SyncJob", back_populates="image", cascade="all, delete-orphan"
    )


class PrismCentral(Base):
    __tablename__ = "prism_centrals"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    api_url = Column(String(512), nullable=False)
    username = Column(String(255), nullable=True)
    password = Column(String(255), nullable=True)
    connected = Column(Boolean, default=False)
    last_checked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    sync_jobs = relationship(
        "SyncJob", back_populates="pc", cascade="all, delete-orphan"
    )


class SyncJob(Base):
    __tablename__ = "sync_jobs"

    id = Column(Integer, primary_key=True, index=True)
    image_id = Column(
        Integer, ForeignKey("images.id", ondelete="CASCADE"), nullable=False
    )
    pc_id = Column(
        Integer, ForeignKey("prism_centrals.id", ondelete="CASCADE"), nullable=False
    )
    status = Column(String(32), default="queued")
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    image = relationship("Image", back_populates="sync_jobs")
    pc = relationship("PrismCentral", back_populates="sync_jobs")
