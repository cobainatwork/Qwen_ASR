import type { TranscribeData } from '@/lib/api/types';
import { formatVttTimestamp } from '@/lib/format/time';
import { buildSegments } from '@/lib/asr/segments';

export function toVtt(data: TranscribeData): string {
  const segs = buildSegments(data.timestamps, data.speakers, data.text);
  const cues = segs
    .map((s) => {
      const start = formatVttTimestamp(s.start);
      const end = formatVttTimestamp(s.end);
      const body = `<v ${s.speaker}>${s.text.trim()}`;
      return `${start} --> ${end}\n${body}`;
    })
    .join('\n\n');
  return `WEBVTT\n\n${cues}\n`;
}
