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
  const wordList: Timestamp[] = timestamps ?? [];
  const hasWords = wordList.length > 0;

  // 無 word-level timestamps（aligner 沒跑 / 超過 5 min 限制）時，speakers 即使有
  // 也無法把全文切到各 turn —— 硬切會誤導使用者；改回單段 SPEAKER_00 含全文。
  const turns: SpeakerTurn[] =
    hasWords && speakers && speakers.length > 0
      ? speakers
      : [{ speaker: 'SPEAKER_00', start: 0, end: wordList.at(-1)?.end ?? 0 }];

  const segments: Segment[] = turns.map((turn) => ({
    speaker: turn.speaker,
    start: turn.start,
    end: turn.end,
    text: '',
    words: [],
  }));

  for (const w of wordList) {
    const idx = segments.findIndex((s) => w.start >= s.start && w.start < s.end);
    let target: Segment;
    if (idx >= 0) {
      target = segments[idx];
    } else if (w.start < segments[0].start) {
      target = segments[0];                            // 前緣 orphan：歸第一段
    } else {
      target = segments[segments.length - 1];          // 後緣 orphan：歸最後一段
    }
    target.words.push(w);
  }

  for (const s of segments) {
    s.text = s.words.length > 0 ? s.words.map((w) => w.text).join('') : '';
  }

  // 無 timestamps 時把 fallbackText 放進唯一一段（呈現原始 ASR text）
  if (!hasWords && segments.length === 1) {
    segments[0].text = fallbackText;
  }

  return segments;
}
