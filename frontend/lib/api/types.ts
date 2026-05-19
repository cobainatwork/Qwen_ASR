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

export interface Timestamp {
  start: number;
  end: number;
  word: string;
}

export interface SpeakerTurn {
  speaker: string;
  start: number;
  end: number;
}

export interface DiarizationInfo {
  status: string;
  backend: string | null;
  speakers_count: number | null;
}

export interface TranscribeData {
  transcription_id: number;
  audio_file_id: number;
  text: string;
  timestamps?: Timestamp[] | null;
  speakers?: SpeakerTurn[] | null;
  diarization?: DiarizationInfo | null;
  language?: string | null;
  duration_sec: number;
  processing_duration_sec: number;
  model_version: string;
  resampling_warning: boolean;
  vad_segments_count: number;
  warnings: string[];
}

export interface YoutubeDownloadData {
  id: number;
  url: string;
  video_title: string | null;
  audio_file_id: number | null;
  status: 'pending' | 'downloading' | 'completed' | 'failed' | string;
  error_message: string | null;
  file_size: number | null;
  duration_sec: number | null;
  created_at: string;
  updated_at: string;
}

export interface YoutubeDownloadRequest {
  url: string;
}
