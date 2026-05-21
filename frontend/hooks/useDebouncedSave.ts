'use client';

import { useEffect, useRef } from 'react';
import { useCorrectionStore } from '@/stores/correctionStore';
import { saveDraft } from '@/lib/correction/draftStore';

interface Options {
  sessionId: number;
  apiKeyId?: number;
  intervalMs?: number;
  mutate: (vars: {
    segmentId: number;
    corrected_text: string;
    expected_version: number;
  }) => Promise<unknown>;
}

export function useDebouncedSave({
  sessionId,
  apiKeyId,
  intervalMs = 2000,
  mutate,
}: Options): void {
  const timersRef = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());
  const draftMap = useCorrectionStore((s) => s.draftMap);

  useEffect(() => {
    draftMap.forEach((draft, segmentId) => {
      const state = useCorrectionStore.getState().saveStates.get(segmentId);
      if (state !== 'unsaved') return;

      const existing = timersRef.current.get(segmentId);
      if (existing) clearTimeout(existing);

      const timer = setTimeout(async () => {
        timersRef.current.delete(segmentId);
        useCorrectionStore.getState().markSaveState(segmentId, 'saving');

        if (apiKeyId != null) {
          await saveDraft(
            { apiKeyId, sessionId, segmentId },
            { text: draft.text, expectedVersion: draft.expectedVersion, syncStatus: 'pending' },
          );
        }

        try {
          await mutate({
            segmentId,
            corrected_text: draft.text,
            expected_version: draft.expectedVersion,
          });
          useCorrectionStore.getState().markSaveState(segmentId, 'saved');
          if (apiKeyId != null) {
            await saveDraft(
              { apiKeyId, sessionId, segmentId },
              { text: draft.text, expectedVersion: draft.expectedVersion, syncStatus: 'synced' },
            );
          }
        } catch (e: unknown) {
          const err = e as { code?: string; status?: number } | null;
          if (
            err?.code === 'CORRECTION_VERSION_MISMATCH' ||
            err?.status === 409
          ) {
            useCorrectionStore.getState().markSaveState(segmentId, 'conflict');
          } else {
            useCorrectionStore.getState().markSaveState(segmentId, 'unsaved');
          }
        }
      }, intervalMs);

      timersRef.current.set(segmentId, timer);
    });
  }, [draftMap, sessionId, apiKeyId, intervalMs, mutate]);

  // Cleanup all pending timers on unmount.
  useEffect(() => {
    return () => {
      timersRef.current.forEach((t) => clearTimeout(t));
      timersRef.current.clear();
    };
  }, []);
}
