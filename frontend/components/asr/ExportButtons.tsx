'use client';

import { Download } from 'lucide-react';

import type { TranscribeData } from '@/lib/api/types';
import { toSrt } from '@/lib/export/srt';
import { toVtt } from '@/lib/export/vtt';
import { toJson } from '@/lib/export/json';
import { triggerDownload } from '@/lib/export/download';

interface Props {
  data: TranscribeData;
  baseFilename?: string;
}

export function ExportButtons({ data, baseFilename = 'transcription' }: Props) {
  const handle = (format: 'srt' | 'vtt' | 'json') => {
    const content =
      format === 'srt' ? toSrt(data) : format === 'vtt' ? toVtt(data) : toJson(data);
    const mime = format === 'json' ? 'application/json' : 'text/plain';
    triggerDownload(`${baseFilename}.${format}`, content, mime);
  };

  return (
    <div className="flex gap-2" role="group" aria-label="Export formats">
      {(['srt', 'vtt', 'json'] as const).map((f) => (
        <button
          key={f}
          type="button"
          onClick={() => handle(f)}
          className="inline-flex items-center gap-1 rounded-lg border border-foreground/15 bg-white/60 backdrop-blur-sm px-3 py-1.5 text-xs font-medium hover:bg-white/80 transition-colors cursor-pointer"
        >
          <Download className="w-3.5 h-3.5" aria-hidden />
          {f.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
