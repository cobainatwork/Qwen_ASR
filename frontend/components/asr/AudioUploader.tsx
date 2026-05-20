'use client';

import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';

import { ApiClient, ApiError } from '@/lib/api/client';
import { LANGUAGE_OPTIONS } from '@/lib/api/languages';
import type { TranscribeData } from '@/lib/api/types';
import { useAuth } from '@/components/auth/useAuth';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';

interface Props {
  onResult: (data: TranscribeData, clientElapsedMs: number) => void;
  onTranscribeStart?: () => void;
  onFileSelected?: (file: File | null) => void;
}

export function AudioUploader({ onResult, onTranscribeStart, onFileSelected }: Props) {
  const { token } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [language, setLanguage] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [elapsedSec, setElapsedSec] = useState(0);

  useEffect(() => {
    if (!loading) {
      setElapsedSec(0);
      return;
    }
    const startedAt = Date.now();
    const id = setInterval(() => {
      setElapsedSec(Math.floor((Date.now() - startedAt) / 1000));
    }, 500);
    return () => clearInterval(id);
  }, [loading]);

  const submit = async () => {
    if (!file) return;
    if (!token) {
      setError('請先在「金鑰」頁設定 API token');
      return;
    }
    onTranscribeStart?.();
    setLoading(true);
    setError(null);
    const client = new ApiClient({ getToken: () => token });
    const startedAt = performance.now();
    try {
      const data = await client.transcribe(
        file,
        { language: language || undefined },
        { idempotencyKey: crypto.randomUUID() },
      );
      const clientElapsedMs = Math.round(performance.now() - startedAt);
      onResult(data, clientElapsedMs);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`${err.code}: ${err.message}`);
      } else {
        setError(err instanceof Error ? err.message : '未知錯誤');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <h2 className="text-lg font-semibold mb-4">上傳音檔</h2>
      <input
        type="file"
        accept="audio/*,video/*"
        onChange={(e) => {
          const f = e.target.files?.[0] ?? null;
          setFile(f);
          onFileSelected?.(f);
        }}
        className="mb-4 block"
        aria-label="選擇音檔"
        disabled={loading}
      />
      <label className="block mb-4">
        <span className="text-sm font-medium mr-2">語言：</span>
        <select
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
          className="border rounded px-2 py-1 bg-white/70"
          aria-label="選擇辨識語言"
          disabled={loading}
        >
          {LANGUAGE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </label>
      <Button onClick={submit} disabled={!file || loading}>
        {loading ? (
          <span className="inline-flex items-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin" />
            辨識中（已 {elapsedSec}s）...
          </span>
        ) : (
          '開始辨識'
        )}
      </Button>
      {loading && elapsedSec >= 30 && (
        <p className="mt-3 text-xs text-foreground/60">
          提示：首次辨識需要載入模型（pyannote 語者分離、ClearVoice 等），約 1-3 分鐘。
          長音檔即使後端模型已載入，VAD + ASR + 對齊 + 語者分離整條 pipeline 也可能需要 2-5 分鐘。
        </p>
      )}
      {error && <p className="mt-4 text-red-500 text-sm">{error}</p>}
    </Card>
  );
}
