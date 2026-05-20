import type { Timestamp, SpeakerTurn } from '@/lib/api/types';

export interface Segment {
  speaker: string;
  start: number;
  end: number;
  text: string;
  words: Timestamp[];
}

export function buildSegments(
  timestamps: Timestamp[] | null | undefined,
  speakers: SpeakerTurn[] | null | undefined,
  fallbackText: string,
): Segment[] {
  const turns: SpeakerTurn[] =
    speakers && speakers.length > 0
      ? speakers
      : [{ speaker: 'SPEAKER_00', start: 0, end: timestamps?.at(-1)?.end ?? 0 }];

  const wordList: Timestamp[] = timestamps ?? [];

  const segments: Segment[] = turns.map((turn) => ({
    speaker: turn.speaker,
    start: turn.start,
    end: turn.end,
    text: '',
    words: [],
  }));

  for (const w of wordList) {
    const idx = segments.findIndex((s) => w.start >= s.start && w.start < s.end);
    const target = idx >= 0 ? segments[idx] : segments[0];
    target.words.push(w);
  }

  for (const s of segments) {
    s.text = s.words.length > 0 ? s.words.map((w) => w.word).join('') : '';
  }

  // 沒 timestamps 時把 fallbackText 放進唯一一段（呈現原始 ASR text）
  if (wordList.length === 0 && segments.length === 1) {
    segments[0].text = fallbackText;
  }

  return segments;
}
