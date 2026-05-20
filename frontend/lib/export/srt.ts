import type { TranscribeData } from '@/lib/api/types';
import { formatSrtTimestamp } from '@/lib/format/time';
import { buildSegments } from '@/lib/asr/segments';

// SRT reserves `\n\n` as cue separator and `-->` as time arrow. Backend transcripts
// can contain newlines (whitespace-pre-wrap rendering) and theoretically `-->`.
// Speaker labels come from pyannote or future custom diarization — untrusted strings.
function sanitizeForSrt(s: string): string {
  return s
    .replace(/\r?\n/g, ' ')
    .replace(/-->/g, '→');
}

export function toSrt(data: TranscribeData): string {
  const segs = buildSegments(data.timestamps, data.speakers, data.text);
  return segs
    .map((s, i) => {
      const start = formatSrtTimestamp(s.start);
      const end = formatSrtTimestamp(s.end);
      const speaker = sanitizeForSrt(s.speaker);
      const trimmed = s.text.trim();
      const text = sanitizeForSrt(trimmed);
      const body = text.length > 0 ? `${speaker}: ${text}` : `${speaker}:`;
      return `${i + 1}\n${start} --> ${end}\n${body}\n`;
    })
    .join('\n');
}
