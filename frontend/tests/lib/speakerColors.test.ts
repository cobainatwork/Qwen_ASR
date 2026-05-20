import { speakerColor, speakerBgColor } from '@/lib/asr/speakerColors';

describe('speakerColor', () => {
  it('回 HSL 字串', () => {
    const c = speakerColor('SPEAKER_00');
    expect(c).toMatch(/^hsl\(\d+(\.\d+)?,\s*\d+%,\s*\d+%\)$/);
  });
  it('同 label 結果穩定', () => {
    expect(speakerColor('SPEAKER_00')).toBe(speakerColor('SPEAKER_00'));
  });
  it('不同 label 不同色（hue 不同）', () => {
    expect(speakerColor('SPEAKER_00')).not.toBe(speakerColor('SPEAKER_01'));
  });
});

describe('speakerBgColor (alpha 較低用於 region 背景)', () => {
  it('回 hsla 字串', () => {
    expect(speakerBgColor('SPEAKER_00')).toMatch(/^hsla\(/);
  });
});
