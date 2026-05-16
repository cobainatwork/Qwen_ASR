from app.models import AudioFile
from app.repositories.base import TenantScopedRepository


class AudioFileRepository(TenantScopedRepository[AudioFile]):
    model = AudioFile

    def set_transcription_id(self, audio_file_id: int, transcription_id: int) -> None:
        af = self.get(audio_file_id)
        if af is None:
            return
        af.transcription_id = transcription_id
        self.db.flush()

    def update_after_resample(
        self,
        audio_file_id: int,
        *,
        original_sample_rate: int,
        duration_sec: float,
    ) -> None:
        af = self.get(audio_file_id)
        if af is None:
            return
        af.original_sample_rate = original_sample_rate
        af.duration_sec = duration_sec
        self.db.flush()
