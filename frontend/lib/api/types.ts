// Auto-generated placeholder. Run `npm run generate-api` against running backend to populate.

// eslint-disable-next-line @typescript-eslint/no-empty-object-type
export interface paths {}
// eslint-disable-next-line @typescript-eslint/no-empty-object-type
export interface components {
  schemas: Record<string, unknown>;
}

// Phase 2 / M6 manual types（在 generate-api 跑前提供基本型別）
export interface ResponseEnvelope<T> {
  success: boolean;
  data: T | null;
  error: { code: string; message: string; details?: Record<string, unknown> } | null;
}

export interface TranscribeOptions {
  language?: string;
  return_timestamps?: boolean;
}

export interface TranscribeData {
  transcription_id: number;
  audio_file_id: number;
  text: string;
  duration_sec: number;
  processing_duration_sec: number;
  model_version: string;
  resampling_warning: boolean;
  vad_segments_count: number;
  warnings: string[];
}
