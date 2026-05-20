import type { TranscribeData } from '@/lib/api/types';

export function toJson(data: TranscribeData): string {
  return JSON.stringify(
    {
      transcription_id: data.transcription_id,
      audio_file_id: data.audio_file_id,
      text: data.text,
      timestamps: data.timestamps ?? [],
      speakers: data.speakers ?? [],
      diarization: data.diarization ?? null,
      language: data.language ?? null,
      duration_sec: data.duration_sec,
      processing_duration_sec: data.processing_duration_sec,
      model_version: data.model_version,
      resampling_warning: data.resampling_warning,
      vad_segments_count: data.vad_segments_count,
      warnings: data.warnings,
    },
    null,
    2,
  );
}
