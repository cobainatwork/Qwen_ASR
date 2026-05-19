'use client';

import { useState } from 'react';

import { TranscriptionResult } from '@/components/asr/TranscriptionResult';
import { YoutubeDownloader } from '@/components/youtube/YoutubeDownloader';
import type { TranscribeData } from '@/lib/api/types';

export default function YoutubePage() {
  const [result, setResult] = useState<TranscribeData | null>(null);

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="max-w-3xl mx-auto">
        <YoutubeDownloader onTranscribed={setResult} />
        {result && <TranscriptionResult data={result} />}
      </div>
    </div>
  );
}
