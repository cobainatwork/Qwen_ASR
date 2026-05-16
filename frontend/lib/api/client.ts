import type { ResponseEnvelope, TranscribeData } from './types';

const DEFAULT_TIMEOUT_MS = 1200_000; // 對齊 backend ASR_REQUEST_TIMEOUT_SEC

interface ApiClientOptions {
  baseUrl?: string;
  getToken?: () => string | null;
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

  async transcribe(file: File, options: { language?: string; return_timestamps?: boolean } = {}): Promise<TranscribeData> {
    const form = new FormData();
    form.append('file', file);
    form.append('options_json', JSON.stringify(options));

    const body = await this.request<TranscribeData>('/api/v1/asr/transcribe', {
      method: 'POST',
      body: form,
    });
    return body;
  }

  private async request<T>(path: string, init: RequestInit): Promise<T> {
    const token = this.getToken();
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);

    try {
      const resp = await fetch(`${this.baseUrl}${path}`, {
        ...init,
        signal: controller.signal,
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
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
