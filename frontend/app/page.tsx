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
      if (!raw) return;
      const parsed: unknown = JSON.parse(raw);
      // Schema guard：早期 commit 直接存 TranscribeData，現在存 { data, clientElapsedMs }。
      // 形狀不符就丟掉，避免 stored.data 為 undefined 時 TranscriptionResult 讀 data.text 炸。
      if (
        parsed !== null &&
        typeof parsed === 'object' &&
        'data' in parsed &&
        parsed.data !== null &&
        typeof parsed.data === 'object' &&
        'text' in parsed.data &&
        'clientElapsedMs' in parsed &&
        typeof (parsed as { clientElapsedMs: unknown }).clientElapsedMs === 'number'
      ) {
        setStored(parsed as StoredResult);
      } else {
        sessionStorage.removeItem(STORAGE_KEY);
      }
    } catch {
      try { sessionStorage.removeItem(STORAGE_KEY); } catch { /* 配額/SecurityError 靜默 */ }
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
