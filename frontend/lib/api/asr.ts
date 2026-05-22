import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useContext, useMemo } from 'react';

import { AuthContext } from '@/components/auth/AuthProvider';
import type { ResponseEnvelope } from './types';

// ─── 型別定義（對齊 app/schemas/asr.py TranscriptionListItem）────────────────

export interface TranscriptionListItem {
  id: number;
  file_name: string | null;
  source: string;
  status: string;
  duration_sec: number | null;
  language: string | null;
  model_version: string;
  created_at: string;
  updated_at: string;
}

export interface TranscriptionListData {
  items: TranscriptionListItem[];
  pagination: {
    total: number;
    page: number;
    limit: number;
    total_pages: number;
  };
}

// ─── API 用戶端 ───────────────────────────────────────────────────────────────

class AsrApiError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = 'AsrApiError';
  }
}

class AsrApi {
  private readonly baseUrl: string;
  private readonly getToken: () => string | null;

  constructor(options: { baseUrl?: string; getToken: () => string | null }) {
    this.baseUrl = options.baseUrl ?? '';
    this.getToken = options.getToken;
  }

  async listTranscriptions(page = 1, limit = 20): Promise<TranscriptionListData> {
    const token = this.getToken();
    const resp = await fetch(
      `${this.baseUrl}/api/v1/asr/transcriptions?page=${page}&limit=${limit}`,
      {
        method: 'GET',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      },
    );
    const json: ResponseEnvelope<TranscriptionListData> = await resp.json();
    if (!json.success || json.data === null) {
      throw new AsrApiError(
        json.error?.code ?? 'UNKNOWN',
        json.error?.message ?? '請求失敗',
        resp.status,
      );
    }
    return json.data;
  }

  /**
   * 硬刪 transcription row + CASCADE correction_sessions + segments。
   * audio_file 保留。
   * DELETE /api/v1/asr/transcriptions/{transcriptionId}
   */
  async deleteTranscription(transcriptionId: number): Promise<void> {
    const token = this.getToken();
    const resp = await fetch(
      `${this.baseUrl}/api/v1/asr/transcriptions/${transcriptionId}`,
      {
        method: 'DELETE',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      },
    );
    if (!resp.ok) {
      let code = 'DELETE_FAILED';
      let message = `刪除失敗（HTTP ${resp.status}）`;
      try {
        const json = await resp.json();
        code = json?.error?.code ?? code;
        message = json?.error?.message ?? message;
      } catch {
        // ignore JSON parse error
      }
      throw new AsrApiError(code, message, resp.status);
    }
  }
}

// ─── TanStack Query hooks ─────────────────────────────────────────────────────

export function useTranscriptionsListQuery(page = 1, limit = 20) {
  const { token } = useContext(AuthContext);
  const api = useMemo(() => new AsrApi({ getToken: () => token }), [token]);
  return useQuery({
    queryKey: ['asr', 'transcriptions', page, limit],
    queryFn: () => api.listTranscriptions(page, limit),
    enabled: token != null,
  });
}

/**
 * DELETE /api/v1/asr/transcriptions/{transcriptionId}
 * 硬刪 transcription，成功後 invalidate transcriptions-list 快取使列表自動刷新。
 */
export function useDeleteTranscriptionMutation() {
  const { token } = useContext(AuthContext);
  const api = useMemo(() => new AsrApi({ getToken: () => token }), [token]);
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (transcriptionId: number) => api.deleteTranscription(transcriptionId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['asr', 'transcriptions'] });
    },
  });
}
