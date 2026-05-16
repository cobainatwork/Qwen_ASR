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

export function AudioUploader({ onResult }: Props) {
  const { token } = useAuth();
  const [file, setFile] = useState<File | null>(null);
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
      const data = await client.transcribe(file, { language: 'zh-TW' });
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
        className="mb-4"
        aria-label="選擇音檔"
      />
      <Button onClick={submit} disabled={!file || loading}>
        {loading ? '辨識中...' : '開始辨識'}
      </Button>
      {error && <p className="mt-4 text-red-500 text-sm">{error}</p>}
    </Card>
  );
}
