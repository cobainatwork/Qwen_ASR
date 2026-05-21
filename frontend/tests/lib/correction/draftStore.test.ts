import { saveDraft, getDraft, listDraftsForSession } from '@/lib/correction/draftStore';

jest.mock('idb-keyval');
import * as idb from 'idb-keyval';

beforeEach(() => {
  // Reset the shared in-memory store between tests
  (idb as any).__store = new Map();
  // Also reset jest mock call histories
  jest.clearAllMocks();
  // Re-wire the set mock to write to the new __store reference
  (idb.set as jest.Mock).mockImplementation(async (key: IDBValidKey, value: unknown) => {
    (idb as any).__store.set(key, value);
  });
  (idb.get as jest.Mock).mockImplementation(async (key: IDBValidKey) =>
    (idb as any).__store.get(key),
  );
  (idb.del as jest.Mock).mockImplementation(async (key: IDBValidKey) => {
    (idb as any).__store.delete(key);
  });
  (idb.entries as jest.Mock).mockImplementation(async () =>
    Array.from((idb as any).__store.entries()),
  );
  (idb.keys as jest.Mock).mockImplementation(async () =>
    Array.from((idb as any).__store.keys()),
  );
});

describe('draftStore', () => {
  it('saveDraft + getDraft 同 key round-trip', async () => {
    await saveDraft(
      { apiKeyId: 1, sessionId: 42, segmentId: 7 },
      { text: 'hello', expectedVersion: 3, syncStatus: 'pending' },
    );
    const d = await getDraft({ apiKeyId: 1, sessionId: 42, segmentId: 7 });
    expect(d).toMatchObject({ text: 'hello', expectedVersion: 3, syncStatus: 'pending' });
  });

  it('apiKey 不同則隔離', async () => {
    await saveDraft(
      { apiKeyId: 1, sessionId: 42, segmentId: 7 },
      { text: 'A', expectedVersion: 1, syncStatus: 'pending' },
    );
    const d = await getDraft({ apiKeyId: 2, sessionId: 42, segmentId: 7 });
    expect(d).toBeNull();
  });

  it('listDraftsForSession 只回該 session', async () => {
    await saveDraft(
      { apiKeyId: 1, sessionId: 42, segmentId: 1 },
      { text: 'a', expectedVersion: 1, syncStatus: 'pending' },
    );
    await saveDraft(
      { apiKeyId: 1, sessionId: 99, segmentId: 1 },
      { text: 'b', expectedVersion: 1, syncStatus: 'pending' },
    );
    const list = await listDraftsForSession({ apiKeyId: 1, sessionId: 42 });
    expect(list).toHaveLength(1);
    expect(list[0].text).toBe('a');
  });

  it('quota error 回 false 不 throw', async () => {
    (idb.set as jest.Mock).mockRejectedValueOnce(
      new DOMException('quota', 'QuotaExceededError'),
    );
    const ok = await saveDraft(
      { apiKeyId: 1, sessionId: 1, segmentId: 1 },
      { text: 'x', expectedVersion: 1, syncStatus: 'pending' },
    );
    expect(ok).toBe(false);
  });
});
