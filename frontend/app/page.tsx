'use client';

import { useEffect, useState } from 'react';

import { AudioUploader } from '@/components/asr/AudioUploader';
import { TranscriptionResult } from '@/components/asr/TranscriptionResult';
import type { TranscribeData } from '@/lib/api/types';

const STORAGE_KEY = 'qwen-asr:last-transcribe-result';

export default function Page() {
  const [result, setResult] = useState<TranscribeData | null>(null);

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (raw) setResult(JSON.parse(raw) as TranscribeData);
    } catch {
      // 解析失敗（手動竄改 / 舊格式），靜默忽略
    }
  }, []);

  const handleResult = (data: TranscribeData) => {
    setResult(data);
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    } catch {
      // 配額或 SecurityError，靜默
    }
  };

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="max-w-2xl mx-auto">
        <AudioUploader onResult={handleResult} />
        {result && <TranscriptionResult data={result} />}
      </div>
    </div>
  );
}
