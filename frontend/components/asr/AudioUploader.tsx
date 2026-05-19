'use client';

import { useState } from 'react';

import { ApiClient, ApiError } from '@/lib/api/client';
import type { TranscribeData } from '@/lib/api/types';
import { useAuth } from '@/components/auth/useAuth';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';

interface Props {
  onResult: (data: TranscribeData) => void;
}

// qwen-asr 0.0.6 只接受英文官方語言名稱或 null（自動偵測）。
// 此清單為前端常用語言，並非完整支援列表。
const LANGUAGE_OPTIONS = [
  { value: '', label: '自動偵測' },
  { value: 'Chinese', label: '中文（國語 / 普通話）' },
  { value: 'Cantonese', label: '粵語' },
  { value: 'English', label: 'English' },
  { value: 'Japanese', label: '日本語' },
  { value: 'Korean', label: '한국어' },
] as const;

export function AudioUploader({ onResult }: Props) {
  const { token } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [language, setLanguage] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!file) return;
    if (!token) {
      setError('請先在「金鑰」頁設定 API token');
      return;
    }
    setLoading(true);
    setError(null);
    const client = new ApiClient({ getToken: () => token });
    try {
      const data = await client.transcribe(file, {
        language: language || undefined,
      });
      onResult(data);
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
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        className="mb-4 block"
        aria-label="選擇音檔"
      />
      <label className="block mb-4">
        <span className="text-sm font-medium mr-2">語言：</span>
        <select
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
          className="border rounded px-2 py-1 bg-white/70"
          aria-label="選擇辨識語言"
        >
          {LANGUAGE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </label>
      <Button onClick={submit} disabled={!file || loading}>
        {loading ? '辨識中...' : '開始辨識'}
      </Button>
      {error && <p className="mt-4 text-red-500 text-sm">{error}</p>}
    </Card>
  );
}
