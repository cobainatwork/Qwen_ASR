import { buildSegments, type Segment } from '@/lib/asr/segments';
import type { Timestamp, SpeakerTurn } from '@/lib/api/types';

describe('buildSegments', () => {
  it('沒 speakers 沒 timestamps：回單一段、空 words、無時間範圍', () => {
    const segs = buildSegments(null, null, '你好世界');
    expect(segs).toHaveLength(1);
    expect(segs[0].speaker).toBe('SPEAKER_00');
    expect(segs[0].words).toEqual([]);
    expect(segs[0].text).toBe('你好世界');
    expect(segs[0].start).toBe(0);
  });

  it('有 timestamps 無 speakers：歸為單一 SPEAKER_00 turn 含全部 words', () => {
    const timestamps: Timestamp[] = [
      { start: 0.0, end: 0.5, word: '你' },
      { start: 0.5, end: 1.0, word: '好' },
    ];
    const segs = buildSegments(timestamps, null, '你好');
    expect(segs).toHaveLength(1);
    expect(segs[0].words).toHaveLength(2);
    expect(segs[0].start).toBe(0.0);
    expect(segs[0].end).toBe(1.0);
  });

  it('有 speakers 有 timestamps：依 turn 範圍切 words', () => {
    const speakers: SpeakerTurn[] = [
      { speaker: 'SPEAKER_00', start: 0, end: 1 },
      { speaker: 'SPEAKER_01', start: 1, end: 2 },
    ];
    const timestamps: Timestamp[] = [
      { start: 0.1, end: 0.5, word: 'A' },
      { start: 0.6, end: 0.9, word: 'B' },
      { start: 1.1, end: 1.5, word: 'C' },
      { start: 1.6, end: 1.9, word: 'D' },
    ];
    const segs = buildSegments(timestamps, speakers, 'A B C D');
    expect(segs).toHaveLength(2);
    expect(segs[0].speaker).toBe('SPEAKER_00');
    expect(segs[0].words.map((w) => w.word)).toEqual(['A', 'B']);
    expect(segs[1].speaker).toBe('SPEAKER_01');
    expect(segs[1].words.map((w) => w.word)).toEqual(['C', 'D']);
  });

  it('word 跨 turn 邊界（落點 < first turn start）：歸到第一 turn', () => {
    const speakers: SpeakerTurn[] = [{ speaker: 'SPEAKER_00', start: 1, end: 2 }];
    const timestamps: Timestamp[] = [{ start: 0.5, end: 0.9, word: 'edge' }];
    const segs = buildSegments(timestamps, speakers, 'edge');
    expect(segs[0].words).toHaveLength(1);
  });

  it('word 落在 last turn end 之後：歸到最後一段（非 segments[0]）', () => {
    const speakers: SpeakerTurn[] = [
      { speaker: 'SPEAKER_00', start: 0, end: 1 },
      { speaker: 'SPEAKER_01', start: 1, end: 2 },
    ];
    const timestamps: Timestamp[] = [{ start: 2.5, end: 3, word: 'tail' }];
    const segs = buildSegments(timestamps, speakers, 'tail');
    expect(segs[1].words.map((w) => w.word)).toContain('tail');
    expect(segs[0].words).toHaveLength(0);
  });

  it('無 timestamps 但有 speakers：忽略 speakers 回單段含全文（不切空段）', () => {
    // 真實情境：長音檔超過 aligner 5 min 限制，timestamps=null 但 diarization 仍跑出多段。
    // 不能硬切（沒對齊資訊無法把全文落到對應 turn），改回單段呈現整段文字。
    const speakers: SpeakerTurn[] = [
      { speaker: 'SPEAKER_00', start: 0, end: 300 },
      { speaker: 'SPEAKER_01', start: 300, end: 600 },
    ];
    const segs = buildSegments(null, speakers, '完整的辨識文字');
    expect(segs).toHaveLength(1);
    expect(segs[0].text).toBe('完整的辨識文字');
  });

  it('空 timestamps array 視同無 timestamps', () => {
    const speakers: SpeakerTurn[] = [
      { speaker: 'SPEAKER_00', start: 0, end: 10 },
      { speaker: 'SPEAKER_01', start: 10, end: 20 },
    ];
    const segs = buildSegments([], speakers, 'fallback');
    expect(segs).toHaveLength(1);
    expect(segs[0].text).toBe('fallback');
  });
});
