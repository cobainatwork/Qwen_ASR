import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useContext, useMemo } from 'react';

import { AuthContext } from '@/components/auth/AuthProvider';
import type { ResponseEnvelope } from './types';

const DEFAULT_TIMEOUT_MS = 1_200_000; // 對齊 M6 client.ts ASR_REQUEST_TIMEOUT_SEC

// ─── 型別定義（對齊 app/schemas/correction.py 1:1）────────────────────────────

export interface CorrectionSession {
  id: number;
  transcription_id: number;
  audio_file_id: number | null;
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
  speaker_label: string | null;
  is_skipped: boolean;
  version: number;
  updated_at: string;
}

export interface UpdateSegmentPayload {
  corrected_text: string;
  expected_version: number;
}

export interface PaginationMeta {
  total: number;
  page: number;
  limit: number;
  total_pages: number;
}

export interface CorrectionSessionListData {
  items: CorrectionSession[];
  pagination: PaginationMeta;
}

export interface CreateCorrectionSessionPayload {
  transcription_id: number;
  name?: string;
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
   * 列出所有校正工作階段（分頁）
   * GET /api/v1/correction/sessions
   */
  async listSessions(
    page: number = 1,
    limit: number = 20,
  ): Promise<CorrectionSessionListData> {
    return this.request<CorrectionSessionListData>(
      `/api/v1/correction/sessions?page=${page}&limit=${limit}`,
      { method: 'GET' },
    );
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

  /**
   * 匯出校正工作階段為 JSONL 格式
   * POST /api/v1/correction/sessions/{session_id}/export-jsonl
   */
  async exportJsonl(sessionId: number): Promise<Blob> {
    return this.requestBlob(
      `/api/v1/correction/sessions/${sessionId}/export-jsonl`,
    );
  }

  /**
   * 匯出校正工作階段為 Excel 格式
   * POST /api/v1/correction/sessions/{session_id}/export-excel
   */
  async exportExcel(sessionId: number): Promise<Blob> {
    return this.requestBlob(
      `/api/v1/correction/sessions/${sessionId}/export-excel`,
    );
  }

  /**
   * 從現有 transcription 建立 correction session（idempotent）
   * POST /api/v1/correction/sessions
   */
  async createSession(payload: CreateCorrectionSessionPayload): Promise<CorrectionSession> {
    return this.request<CorrectionSession>('/api/v1/correction/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  }

  /**
   * 硬刪除校正工作階段（含 segments CASCADE）
   * DELETE /api/v1/correction/sessions/{session_id}
   */
  async deleteSession(sessionId: number): Promise<void> {
    const token = this.getToken();
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);
    try {
      const resp = await fetch(`${this.baseUrl}/api/v1/correction/sessions/${sessionId}`, {
        method: 'DELETE',
        signal: controller.signal,
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!resp.ok) {
        let code = 'DELETE_FAILED';
        let message = `刪除失敗（HTTP ${resp.status}）`;
        try {
          const json = await resp.json();
          code = json?.error?.code ?? code;
          message = json?.error?.message ?? message;
        } catch {
          // ignore parse error
        }
        throw new CorrectionApiError(code, message, resp.status);
      }
    } finally {
      clearTimeout(timer);
    }
  }

  /**
   * 評估工作階段品質
   * POST /api/v1/correction/sessions/{session_id}/evaluate-quality
   */
  async evaluateQuality(
    sessionId: number,
  ): Promise<{ score: number; issues: { code: string; message?: string }[] }> {
    return this.request<{
      score: number;
      issues: { code: string; message?: string }[];
    }>(`/api/v1/correction/sessions/${sessionId}/evaluate-quality`, {
      method: 'POST',
    });
  }

  // ─── 私有工具 ──────────────────────────────────────────────────────────────

  /** Blob 專用請求（跳過 JSON envelope 解析）。 */
  private async requestBlob(path: string): Promise<Blob> {
    const token = this.getToken();
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);
    try {
      const resp = await fetch(`${this.baseUrl}${path}`, {
        method: 'POST',
        signal: controller.signal,
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!resp.ok) {
        // Best-effort：嘗試解析 JSON envelope 取得錯誤碼
        let code = 'EXPORT_FAILED';
        let message = `匯出失敗（HTTP ${resp.status}）`;
        try {
          const json = await resp.json();
          code = json?.error?.code ?? code;
          message = json?.error?.message ?? message;
        } catch {
          // ignore parse error
        }
        throw new CorrectionApiError(code, message, resp.status);
      }
      return resp.blob();
    } finally {
      clearTimeout(timer);
    }
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

// ─── TanStack Query hooks（A3 主用） ──────────────────────────────────────────

/**
 * GET /api/v1/correction/sessions
 * 列出所有校正工作階段（分頁）
 */
export function useCorrectionSessionsListQuery(
  page: number = 1,
  limit: number = 20,
) {
  const { token } = useContext(AuthContext);
  const api = useMemo(() => new CorrectionApi({ getToken: () => token }), [token]);
  return useQuery({
    queryKey: ['correction', 'sessions-list', page, limit],
    queryFn: () => api.listSessions(page, limit),
    enabled: token != null,
  });
}

/**
 * GET /api/v1/correction/sessions/{sessionId}
 * 取得校正工作階段詳情
 */
export function useCorrectionSessionQuery(sessionId: number) {
  const { token } = useContext(AuthContext);
  const api = useMemo(() => new CorrectionApi({ getToken: () => token }), [token]);
  return useQuery({
    queryKey: ['correction', 'session', sessionId],
    queryFn: () => api.getSession(sessionId),
    enabled: token != null && Number.isFinite(sessionId),
  });
}

/**
 * GET /api/v1/correction/sessions/{sessionId}/segments
 * 列出工作階段所有校正片段
 */
export function useCorrectionSegmentsQuery(sessionId: number) {
  const { token } = useContext(AuthContext);
  const api = useMemo(() => new CorrectionApi({ getToken: () => token }), [token]);
  return useQuery({
    queryKey: ['correction', 'segments', sessionId],
    queryFn: () => api.listSegments(sessionId),
    enabled: token != null && Number.isFinite(sessionId),
  });
}

/**
 * PUT /api/v1/correction/sessions/{sessionId}/segments/{segmentId}
 * 更新單一校正片段（含 optimistic locking），成功後自動 invalidate segments 快取
 */
export function useUpdateSegmentMutation(sessionId: number) {
  const { token } = useContext(AuthContext);
  const api = useMemo(() => new CorrectionApi({ getToken: () => token }), [token]);
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: {
      segmentId: number;
      corrected_text: string | null;
      expected_version: number;
      is_skipped?: boolean;
    }) =>
      api.updateSegment(sessionId, vars.segmentId, {
        corrected_text: vars.corrected_text ?? '',
        expected_version: vars.expected_version,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['correction', 'segments', sessionId] });
    },
  });
}

/**
 * POST /api/v1/correction/sessions/{sessionId}/export-jsonl
 * 匯出 JSONL Blob
 */
export function useExportJsonlMutation(sessionId: number) {
  const { token } = useContext(AuthContext);
  const api = useMemo(() => new CorrectionApi({ getToken: () => token }), [token]);
  return useMutation({
    mutationFn: () => api.exportJsonl(sessionId),
  });
}

/**
 * POST /api/v1/correction/sessions/{sessionId}/export-excel
 * 匯出 Excel Blob
 */
export function useExportExcelMutation(sessionId: number) {
  const { token } = useContext(AuthContext);
  const api = useMemo(() => new CorrectionApi({ getToken: () => token }), [token]);
  return useMutation({
    mutationFn: () => api.exportExcel(sessionId),
  });
}

/**
 * POST /api/v1/correction/sessions/{sessionId}/evaluate-quality
 * 品質評估
 */
export function useEvaluateQualityMutation(sessionId: number) {
  const { token } = useContext(AuthContext);
  const api = useMemo(() => new CorrectionApi({ getToken: () => token }), [token]);
  return useMutation({
    mutationFn: () => api.evaluateQuality(sessionId),
  });
}

/**
 * DELETE /api/v1/correction/sessions/{sessionId}
 * 硬刪除校正工作階段，成功後 invalidate sessions list
 */
export function useDeleteCorrectionSessionMutation() {
  const { token } = useContext(AuthContext);
  const api = useMemo(() => new CorrectionApi({ getToken: () => token }), [token]);
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: number) => api.deleteSession(sessionId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['correction', 'sessions-list'] });
    },
  });
}

/**
 * POST /api/v1/correction/sessions
 * 從 transcription 建立（或取回既有）correction session，成功後 invalidate sessions list
 */
export function useCreateCorrectionSessionMutation() {
  const { token } = useContext(AuthContext);
  const api = useMemo(() => new CorrectionApi({ getToken: () => token }), [token]);
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateCorrectionSessionPayload) => api.createSession(payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['correction', 'sessions-list'] });
    },
  });
}
