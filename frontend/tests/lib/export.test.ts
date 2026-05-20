import { toSrt } from '@/lib/export/srt';
import { toVtt } from '@/lib/export/vtt';
import { toJson } from '@/lib/export/json';
import { sanitizeFilename } from '@/lib/export/download';
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

describe('toSrt sanitization', () => {
  it('newline in text becomes space (preserves single cue)', () => {
    const data: TranscribeData = {
      transcription_id: 1, audio_file_id: 2, text: 'a\nb',
      timestamps: [{ start: 0, end: 1, word: 'a\nb' }],
      speakers: null, diarization: null, language: null,
      duration_sec: 1, processing_duration_sec: 0, model_version: 'T',
      resampling_warning: false, vad_segments_count: 1, warnings: [],
    };
    const srt = toSrt(data);
    expect(srt).toContain('SPEAKER_00: a b');
    expect(srt).not.toContain('a\nb');
  });

  it('--> in text becomes → (preserves cue structure)', () => {
    const data: TranscribeData = {
      transcription_id: 1, audio_file_id: 2, text: 'foo --> bar',
      timestamps: [{ start: 0, end: 1, word: 'foo --> bar' }],
      speakers: null, diarization: null, language: null,
      duration_sec: 1, processing_duration_sec: 0, model_version: 'T',
      resampling_warning: false, vad_segments_count: 1, warnings: [],
    };
    const srt = toSrt(data);
    expect(srt).toContain('foo → bar');
    expect(srt.match(/-->/g)?.length).toBe(1); // 只有時間軸那一個 -->
  });
});

describe('sanitizeFilename', () => {
  it('strips slashes', () => {
    expect(sanitizeFilename('a/b\\c.srt')).toBe('a_b_c.srt');
  });
  it('strips dotdot sequences', () => {
    expect(sanitizeFilename('../../etc/passwd')).toBe('____etc_passwd');
  });
  it('strips control chars (space and dash)', () => {
    expect(sanitizeFilename('a b.srt')).toBe('a_b.srt');
  });
  it('caps length at 200', () => {
    expect(sanitizeFilename('a'.repeat(300)).length).toBe(200);
  });
});

describe('toVtt sanitization', () => {
  it('HTML-escapes speaker name', () => {
    const data: TranscribeData = {
      transcription_id: 1, audio_file_id: 2, text: 'hi',
      timestamps: [{ start: 0, end: 1, word: 'hi' }],
      speakers: [{ speaker: '<script>', start: 0, end: 1 }],
      diarization: null, language: null,
      duration_sec: 1, processing_duration_sec: 0, model_version: 'T',
      resampling_warning: false, vad_segments_count: 1, warnings: [],
    };
    const vtt = toVtt(data);
    expect(vtt).toContain('&lt;script&gt;');
    expect(vtt).not.toContain('<script>');
  });

  it('closes <v> tag with </v>', () => {
    const data: TranscribeData = {
      transcription_id: 1, audio_file_id: 2, text: 'hi',
      timestamps: [{ start: 0, end: 1, word: 'hi' }],
      speakers: null, diarization: null, language: null,
      duration_sec: 1, processing_duration_sec: 0, model_version: 'T',
      resampling_warning: false, vad_segments_count: 1, warnings: [],
    };
    const vtt = toVtt(data);
    expect(vtt).toContain('</v>');
  });
});
