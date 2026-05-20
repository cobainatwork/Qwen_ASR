import type { TranscribeData } from '@/lib/api/types';
import { formatSrtTimestamp } from '@/lib/format/time';
import { buildSegments } from '@/lib/asr/segments';

export function toSrt(data: TranscribeData): string {
  const segs = buildSegments(data.timestamps, data.speakers, data.text);
  return segs
    .map((s, i) => {
      const start = formatSrtTimestamp(s.start);
      const end = formatSrtTimestamp(s.end);
      const body = s.text.trim().length > 0 ? `${s.speaker}: ${s.text.trim()}` : `${s.speaker}:`;
      return `${i + 1}\n${start} --> ${end}\n${body}\n`;
    })
    .join('\n');
}
