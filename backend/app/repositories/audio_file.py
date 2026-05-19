from app.models import AudioFile
from app.repositories.base import TenantScopedRepository


class AudioFileRepository(TenantScopedRepository[AudioFile]):
    model = AudioFile

    def lock_for_processing(self, audio_file_id: int) -> AudioFile | None:
        """SELECT ... FOR UPDATE 取得 audio_files row 的 row-level lock。

        Tenant isolation 透過 _scoped_query 過濾。commit / rollback 前其他
        transaction 對同 row 呼叫 lock_for_processing 會阻塞，序列化執行。
        """
        return (
            self._scoped_query()
            .filter(self.model.id == audio_file_id)
            .with_for_update()
            .one_or_none()
        )

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
