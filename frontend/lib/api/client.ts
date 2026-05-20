import type { ResponseEnvelope, TranscribeData, YoutubeDownloadData } from './types';

const DEFAULT_TIMEOUT_MS = 1200_000; // 對齊 backend ASR_REQUEST_TIMEOUT_SEC

interface ApiClientOptions {
  baseUrl?: string;
  getToken?: () => string | null;
}

interface RequestExtras {
  idempotencyKey?: string;
}

export class ApiError extends Error {
  constructor(public code: string, message: string, public status: number) {
    super(message);
    this.name = 'ApiError';
  }
}

export class ApiClient {
  private baseUrl: string;
  private getToken: () => string | null;

  constructor(options: ApiClientOptions = {}) {
    this.baseUrl = options.baseUrl ?? '';
    this.getToken = options.getToken ?? (() => null);
  }

  async transcribe(
    file: File,
    options: { language?: string; return_timestamps?: boolean } = {},
    extras: RequestExtras = {},
  ): Promise<TranscribeData> {
    const form = new FormData();
    form.append('file', file);
    form.append('options_json', JSON.stringify(options));

    const body = await this.request<TranscribeData>(
      '/api/v1/asr/transcribe',
      { method: 'POST', body: form },
      extras,
    );
    return body;
  }

  /** 對既存 audio_file 重跑 ASR（不需 re-upload），用於 YouTube 下載完成後一鍵辨識。 */
  async transcribeStored(
    audioFileId: number,
    options: { language?: string; return_timestamps?: boolean } = {},
    extras: RequestExtras = {},
  ): Promise<TranscribeData> {
    const form = new FormData();
    form.append('options_json', JSON.stringify(options));
    return this.request<TranscribeData>(
      `/api/v1/asr/transcribe-stored/${audioFileId}`,
      { method: 'POST', body: form },
      extras,
    );
  }

  async youtubeDownload(url: string, extras: RequestExtras = {}): Promise<YoutubeDownloadData> {
    return this.request<YoutubeDownloadData>(
      '/api/v1/dataset/youtube/download',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      },
      extras,
    );
  }

  async listYoutubeDownloads(
    options: { limit?: number; offset?: number } = {},
  ): Promise<YoutubeDownloadData[]> {
    const params = new URLSearchParams();
    if (options.limit !== undefined) params.set('limit', String(options.limit));
    if (options.offset !== undefined) params.set('offset', String(options.offset));
    const query = params.toString() ? `?${params.toString()}` : '';
    return this.request<YoutubeDownloadData[]>(
      `/api/v1/dataset/youtube/downloads${query}`,
      { method: 'GET' },
    );
  }

  async getYoutubeDownload(id: number): Promise<YoutubeDownloadData> {
    return this.request<YoutubeDownloadData>(
      `/api/v1/dataset/youtube/downloads/${id}`,
      { method: 'GET' },
    );
  }

  private async request<T>(path: string, init: RequestInit, extras: RequestExtras = {}): Promise<T> {
    const token = this.getToken();
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);

    try {
      const resp = await fetch(`${this.baseUrl}${path}`, {
        ...init,
        signal: controller.signal,
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...(extras.idempotencyKey ? { 'Idempotency-Key': extras.idempotencyKey } : {}),
          ...(init.headers ?? {}),
        },
      });
      const json: ResponseEnvelope<T> = await resp.json();
      if (!json.success || json.data === null) {
        throw new ApiError(json.error?.code ?? 'UNKNOWN', json.error?.message ?? 'Request failed', resp.status);
      }
      return json.data;
    } finally {
      clearTimeout(timer);
    }
  }
}
