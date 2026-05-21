'use client';

import { useEffect } from 'react';
import {
  useCorrectionSessionQuery,
  useCorrectionSegmentsQuery,
  useUpdateSegmentMutation,
} from '@/lib/api/correction';
import { useCorrectionStore } from '@/stores/correctionStore';
import { useDebouncedSave } from './useDebouncedSave';

export function useCorrectionSession(sessionId: number, apiKeyId?: number) {
  const sessionQ = useCorrectionSessionQuery(sessionId);
  const segmentsQ = useCorrectionSegmentsQuery(sessionId);
  const updateM = useUpdateSegmentMutation(sessionId);

  useEffect(() => {
    useCorrectionStore.getState().setSession(sessionId);
    return () => {
      useCorrectionStore.getState().reset();
    };
  }, [sessionId]);

  useDebouncedSave({
    sessionId,
    apiKeyId,
    mutate: updateM.mutateAsync,
  });

  return {
    session: sessionQ.data,
    segments: segmentsQ.data ?? [],
    isLoading: sessionQ.isLoading || segmentsQ.isLoading,
    error: sessionQ.error ?? segmentsQ.error,
  };
}
