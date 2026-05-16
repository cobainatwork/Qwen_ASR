from datetime import datetime
from typing import Any

from sqlalchemy import ARRAY, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin


class Transcription(Base, TenantMixin):
    __tablename__ = "transcriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    transcript_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamps: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    speakers: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    normalized_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    post_processing: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default="processing")
    processing_duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    hotword_group_ids: Mapped[list[int] | None] = mapped_column(ARRAY(Integer), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
        onupdate="now()",
    )
