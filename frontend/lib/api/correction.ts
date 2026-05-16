import type { ResponseEnvelope } from './types';

// ─── 型別定義 ────────────────────────────────────────────────────────────────

export interface CorrectionSession {
  session_id: number;
  transcription_id: number;
  status: 'pending' | 'in_progress' | 'completed' | 'exported';
  created_at: string;
  updated_at: string;
}

export interface CorrectionSegment {
  segment_id: number;
  session_id: number;
  start_sec: number;
  end_sec: number;
  speaker_label: string | null;
  original_text: string;
  corrected_text: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface UpdateSegmentPayload {
  corrected_text: string;
  expected_version: number;
}

export interface ExportToDatasetPayload {
  dataset_name: string;
  description?: string;
}

export interface ExportResult {
  dataset_id: number;
  inserted_count: number;
  dataset_name: string;
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
   * PUT /api/v1/correction/segments/{segment_id}
   */
  async updateSegment(
    segmentId: number,
    payload: UpdateSegmentPayload,
  ): Promise<CorrectionSegment> {
    return this.request<CorrectionSegment>(
      `/api/v1/correction/segments/${segmentId}`,
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
    const resp = await fetch(`${this.baseUrl}${path}`, {
      ...init,
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
  }
}
