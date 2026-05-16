import type { ResponseEnvelope } from './types';

const DEFAULT_TIMEOUT_MS = 1_200_000; // 對齊 M6 client.ts ASR_REQUEST_TIMEOUT_SEC

// ─── 型別定義（對齊 app/schemas/correction.py 1:1）────────────────────────────

export interface CorrectionSession {
  id: number;
  transcription_id: number;
  name: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface CorrectionSegment {
  id: number;
  session_id: number;
  segment_index: number;
  start_sec: number;
  end_sec: number;
  original_text: string;
  corrected_text: string | null;
  version: number;
  updated_at: string;
}

export interface UpdateSegmentPayload {
  corrected_text: string;
  expected_version: number;
}

export interface ExportToDatasetPayload {
  dataset_id: number;
}

export interface ExportResult {
  inserted_count: number;
  dataset_id: number;
}

// ─── API 用戶端 ───────────────────────────────────────────────────────────────

interface CorrectionApiOptions {
  baseUrl?: string;
  getToken: () => string | null;
}

export class CorrectionApiError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = 'CorrectionApiError';
  }
}

export class CorrectionApi {
  private readonly baseUrl: string;
  private readonly getToken: () => string | null;

  constructor(options: CorrectionApiOptions) {
    this.baseUrl = options.baseUrl ?? '';
    this.getToken = options.getToken;
  }

  /**
   * 取得校正工作階段詳情
   * GET /api/v1/correction/sessions/{session_id}
   */
  async getSession(sessionId: number): Promise<CorrectionSession> {
    return this.request<CorrectionSession>(
      `/api/v1/correction/sessions/${sessionId}`,
      { method: 'GET' },
    );
  }

  /**
   * 列出工作階段的所有校正片段
   * GET /api/v1/correction/sessions/{session_id}/segments
   */
  async listSegments(sessionId: number): Promise<CorrectionSegment[]> {
    return this.request<CorrectionSegment[]>(
      `/api/v1/correction/sessions/${sessionId}/segments`,
      { method: 'GET' },
    );
  }

  /**
   * 更新單一校正片段（含 optimistic locking）
   * PUT /api/v1/correction/sessions/{session_id}/segments/{segment_id}
   */
  async updateSegment(
    sessionId: number,
    segmentId: number,
    payload: UpdateSegmentPayload,
  ): Promise<CorrectionSegment> {
    return this.request<CorrectionSegment>(
      `/api/v1/correction/sessions/${sessionId}/segments/${segmentId}`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
    );
  }

  /**
   * 將已校正工作階段匯出至 Fine-tune 資料集
   * POST /api/v1/correction/sessions/{session_id}/export-to-dataset
   */
  async exportToDataset(
    sessionId: number,
    payload: ExportToDatasetPayload,
  ): Promise<ExportResult> {
    return this.request<ExportResult>(
      `/api/v1/correction/sessions/${sessionId}/export-to-dataset`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
    );
  }

  // ─── 私有工具 ──────────────────────────────────────────────────────────────

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
        throw new CorrectionApiError(
          json.error?.code ?? 'UNKNOWN',
          json.error?.message ?? '請求失敗',
          resp.status,
        );
      }
      return json.data;
    } finally {
      clearTimeout(timer);
    }
  }
}
