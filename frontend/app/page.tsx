'use client';

import { useState } from 'react';

import { AudioUploader } from '@/components/asr/AudioUploader';
import { TranscriptionResult } from '@/components/asr/TranscriptionResult';
import type { TranscribeData } from '@/lib/api/types';

export default function Page() {
  const [result, setResult] = useState<TranscribeData | null>(null);

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="max-w-2xl mx-auto">
        <AudioUploader onResult={setResult} />
        {result && <TranscriptionResult data={result} />}
      </div>
    </div>
  );
}
