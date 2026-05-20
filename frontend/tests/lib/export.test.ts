import { toSrt } from '@/lib/export/srt';
import { toVtt } from '@/lib/export/vtt';
import { toJson } from '@/lib/export/json';
import type { TranscribeData } from '@/lib/api/types';

const baseData: TranscribeData = {
  transcription_id: 1,
  audio_file_id: 2,
  text: '你好 世界',
  timestamps: [
    { start: 0.0, end: 0.8, word: '你好' },
    { start: 1.0, end: 2.0, word: '世界' },
  ],
  speakers: [
    { speaker: 'SPEAKER_00', start: 0, end: 1 },
    { speaker: 'SPEAKER_01', start: 1, end: 2 },
  ],
  diarization: null,
  language: 'zh',
  duration_sec: 2.0,
  processing_duration_sec: 0.5,
  model_version: 'TEST',
  resampling_warning: false,
  vad_segments_count: 2,
  warnings: [],
};

describe('toSrt', () => {
  it('每 speaker turn 一個 cue', () => {
    const srt = toSrt(baseData);
    expect(srt).toContain('1\n00:00:00,000 --> 00:00:01,000\nSPEAKER_00: 你好\n');
    expect(srt).toContain('2\n00:00:01,000 --> 00:00:02,000\nSPEAKER_01: 世界\n');
  });
});

describe('toVtt', () => {
  it('開頭 WEBVTT，cue 用 . 分隔毫秒', () => {
    const vtt = toVtt(baseData);
    expect(vtt.startsWith('WEBVTT\n\n')).toBe(true);
    expect(vtt).toContain('00:00:00.000 --> 00:00:01.000');
    expect(vtt).toContain('<v SPEAKER_00>你好');
  });
});

describe('toJson', () => {
  it('合法 JSON、含核心欄位', () => {
    const json = toJson(baseData);
    const parsed = JSON.parse(json);
    expect(parsed.text).toBe('你好 世界');
    expect(parsed.timestamps).toHaveLength(2);
    expect(parsed.speakers).toHaveLength(2);
    expect(parsed.duration_sec).toBe(2.0);
  });
});
