import type { TranscribeData } from '@/lib/api/types';
import { formatVttTimestamp } from '@/lib/format/time';
import { buildSegments } from '@/lib/asr/segments';

// WebVTT reserves `\n\n` as cue separator and `-->` as time arrow.
// `<v Speaker>` is a voice tag — `<`, `>`, `&` in speaker name break parsing.
function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function sanitizeForVtt(s: string): string {
  return s
    .replace(/\r?\n/g, ' ')
    .replace(/-->/g, '→');
}

export function toVtt(data: TranscribeData): string {
  const segs = buildSegments(data.timestamps, data.speakers, data.text);
  const cues = segs
    .map((s) => {
      const start = formatVttTimestamp(s.start);
      const end = formatVttTimestamp(s.end);
      const speakerEscaped = escapeHtml(sanitizeForVtt(s.speaker));
      const textEscaped = escapeHtml(sanitizeForVtt(s.text.trim()));
      // WebVTT 規範允許 inline `<v>` 不需閉合，但顯式 `</v>` 更穩妥相容下游 parser
      const body = `<v ${speakerEscaped}>${textEscaped}</v>`;
      return `${start} --> ${end}\n${body}`;
    })
    .join('\n\n');
  return `WEBVTT\n\n${cues}\n`;
}
