import { computeDiff } from '@/lib/correction/diff';

describe('computeDiff', () => {
  it('短段字元級', () => {
    const ops = computeDiff('hello', 'hallo');
    expect(ops.find((o) => o.type === 'delete' && o.text === 'e')).toBeTruthy();
    expect(ops.find((o) => o.type === 'insert' && o.text === 'a')).toBeTruthy();
  });

  it('長段詞級（>200 字元）', () => {
    const long = 'a'.repeat(250);
    const ops = computeDiff(long, long.replace('a', 'b'));
    // 詞級不應拆到字元
    expect(ops.length).toBeLessThan(long.length);
  });

  it('相同字串無 diff', () => {
    const ops = computeDiff('same', 'same');
    expect(ops.every((o) => o.type === 'equal')).toBe(true);
  });
});
