'use client';

import { useEffect, useState } from 'react';

import { AudioUploader } from '@/components/asr/AudioUploader';
import { TranscriptionResult } from '@/components/asr/TranscriptionResult';
import type { TranscribeData } from '@/lib/api/types';

const STORAGE_KEY = 'qwen-asr:last-transcribe-result';

type StoredResult = { data: TranscribeData; clientElapsedMs: number };

export default function Page() {
  const [stored, setStored] = useState<StoredResult | null>(null);

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (raw) setStored(JSON.parse(raw) as StoredResult);
    } catch {
      // 解析失敗（手動竄改 / 舊格式），靜默忽略
    }
  }, []);

  const handleTranscribeStart = () => {
    setStored(null);
    try {
      sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      // 靜默
    }
  };

  const handleResult = (data: TranscribeData, clientElapsedMs: number) => {
    const next: StoredResult = { data, clientElapsedMs };
    setStored(next);
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      // 配額或 SecurityError，靜默
    }
  };

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="max-w-2xl mx-auto">
        <AudioUploader onResult={handleResult} onTranscribeStart={handleTranscribeStart} />
        {stored && (
          <TranscriptionResult data={stored.data} clientElapsedMs={stored.clientElapsedMs} />
        )}
      </div>
    </div>
  );
}
