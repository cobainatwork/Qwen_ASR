import { createStore, del, entries, get, set } from 'idb-keyval';

const STORE = createStore('correction-drafts', 'drafts');

export interface DraftKey {
  apiKeyId: number;
  sessionId: number;
  segmentId: number;
}

export interface DraftValue {
  text: string;
  expectedVersion: number;
  syncStatus: 'pending' | 'synced' | 'conflict';
  updatedAt?: number;
}

function buildKey({ apiKeyId, sessionId, segmentId }: DraftKey): string {
  return `${apiKeyId}:${sessionId}:${segmentId}`;
}

export async function saveDraft(key: DraftKey, value: DraftValue): Promise<boolean> {
  try {
    await set(buildKey(key), { ...value, updatedAt: Date.now() }, STORE);
    return true;
  } catch (e) {
    if (e instanceof DOMException && e.name === 'QuotaExceededError') {
      return false;
    }
    throw e;
  }
}

export async function getDraft(key: DraftKey): Promise<DraftValue | null> {
  const v = await get(buildKey(key), STORE);
  return (v as DraftValue) ?? null;
}

export async function deleteDraft(key: DraftKey): Promise<void> {
  await del(buildKey(key), STORE);
}

export async function listDraftsForSession({
  apiKeyId,
  sessionId,
}: Omit<DraftKey, 'segmentId'>): Promise<Array<DraftValue & { segmentId: number }>> {
  const prefix = `${apiKeyId}:${sessionId}:`;
  const allEntries = await entries(STORE);
  return allEntries
    .filter(([k]) => typeof k === 'string' && (k as string).startsWith(prefix))
    .map(([k, v]) => ({
      ...(v as DraftValue),
      segmentId: Number((k as string).slice(prefix.length)),
    }));
}

export async function cleanupSynced(
  olderThanMs: number = 7 * 24 * 60 * 60 * 1000,
): Promise<void> {
  const cutoff = Date.now() - olderThanMs;
  const allEntries = await entries(STORE);
  for (const [k, v] of allEntries) {
    const d = v as DraftValue;
    if (d.syncStatus === 'synced' && (d.updatedAt ?? 0) < cutoff) {
      await del(k, STORE);
    }
  }
}
