import { randomUuid } from '@/lib/uuid';

const UUID_V4_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

describe('randomUuid', () => {
  it('回 RFC 4122 v4 UUID 格式', () => {
    expect(randomUuid()).toMatch(UUID_V4_RE);
  });

  it('連續呼叫產生不同值（隨機強度足夠）', () => {
    const a = randomUuid();
    const b = randomUuid();
    expect(a).not.toBe(b);
  });

  it('crypto.randomUUID 不存在時走 getRandomValues fallback 仍合法', () => {
    const original = globalThis.crypto.randomUUID;
    // @ts-expect-error 暫移除以觸發 fallback path
    delete globalThis.crypto.randomUUID;
    try {
      const v = randomUuid();
      expect(v).toMatch(UUID_V4_RE);
    } finally {
      globalThis.crypto.randomUUID = original;
    }
  });
});
