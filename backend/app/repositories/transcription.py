from typing import Any

from app.models import Transcription
from app.repositories.base import TenantScopedRepository


class TranscriptionRepository(TenantScopedRepository[Transcription]):
    model = Transcription

    def mark_completed(
        self,
        transcription_id: int,
        *,
        transcript_text: str,
        timestamps: list[dict[str, Any]] | None,
        processing_duration_sec: float,
    ) -> None:
        rec = self.get(transcription_id)
        if rec is None:
            return
        rec.transcript_text = transcript_text
        rec.timestamps = timestamps
        rec.processing_duration_sec = processing_duration_sec
        rec.status = "completed"
        self.db.flush()

    def mark_failed(self, transcription_id: int, *, error_message: str) -> None:
        rec = self.get(transcription_id)
        if rec is None:
            return
        rec.status = "failed"
        rec.error_message = error_message
        self.db.flush()
