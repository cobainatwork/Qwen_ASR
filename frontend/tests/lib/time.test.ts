import { formatTimestamp, formatDuration, formatSrtTimestamp, formatVttTimestamp } from '@/lib/format/time';

describe('formatTimestamp (短形 mm:ss.s)', () => {
  it('零秒', () => expect(formatTimestamp(0)).toBe('00:00.0'));
  it('1.2 秒', () => expect(formatTimestamp(1.2)).toBe('00:01.2'));
  it('整數分', () => expect(formatTimestamp(60)).toBe('01:00.0'));
  it('跨小時也用 mm:ss', () => expect(formatTimestamp(3661.5)).toBe('61:01.5'));
  it('負值 clamp 為 0', () => expect(formatTimestamp(-1)).toBe('00:00.0'));
});

describe('formatDuration (顯示總長 mm:ss / hh:mm:ss)', () => {
  it('1 分鐘以下顯示 ss 秒', () => expect(formatDuration(45.6)).toBe('00:45'));
  it('小於 1 小時 mm:ss', () => expect(formatDuration(754)).toBe('12:34'));
  it('超過 1 小時 hh:mm:ss', () => expect(formatDuration(3725)).toBe('01:02:05'));
});

describe('formatSrtTimestamp (00:00:00,000)', () => {
  it('1.234 秒', () => expect(formatSrtTimestamp(1.234)).toBe('00:00:01,234'));
  it('跨小時', () => expect(formatSrtTimestamp(3661.5)).toBe('01:01:01,500'));
});

describe('formatVttTimestamp (00:00:00.000)', () => {
  it('1.234 秒', () => expect(formatVttTimestamp(1.234)).toBe('00:00:01.234'));
  it('跨小時', () => expect(formatVttTimestamp(3661.5)).toBe('01:01:01.500'));
});

describe('formatTimestamp 非有限數', () => {
  it('NaN → 00:00.0', () => expect(formatTimestamp(NaN)).toBe('00:00.0'));
  it('Infinity → 00:00.0', () => expect(formatTimestamp(Infinity)).toBe('00:00.0'));
  it('-Infinity → 00:00.0', () => expect(formatTimestamp(-Infinity)).toBe('00:00.0'));
});
