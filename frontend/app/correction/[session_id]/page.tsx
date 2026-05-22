'use client';

import { useContext, useMemo, useRef } from 'react';
import { useParams } from 'next/navigation';

import { AuthContext } from '@/components/auth/AuthProvider';
import { useCorrectionSession } from '@/hooks/useCorrectionSession';
import { useCorrectionShortcuts } from '@/hooks/useCorrectionShortcuts';
import { useCorrectionStore } from '@/stores/correctionStore';
import { useUpdateSegmentMutation } from '@/lib/api/correction';
import { CorrectionLayout } from '@/components/correction/CorrectionLayout';
import {
  CorrectionAudioPanel,
  type CorrectionAudioPanelHandle,
} from '@/components/correction/audio/CorrectionAudioPanel';
import { SegmentList } from '@/components/correction/list/SegmentList';
import { SegmentEditorCardList } from '@/components/correction/editor/SegmentEditorCard';
import { CorrectionToolbar } from '@/components/correction/CorrectionToolbar';

export default function CorrectionWorkbenchPage() {
  const { session_id } = useParams<{ session_id: string }>();
  const { token } = useContext(AuthContext);
  const sessionId = Number(session_id);

  // apiKeyId is not exposed by AuthContext in V1; hook accepts it as optional
  const { session, segments: rawSegments, isLoading, error } = useCorrectionSession(sessionId, undefined);
  // Stabilise the segments array reference: useCorrectionSession returns
  // `segmentsQ.data ?? []` which creates a new [] each render when data is
  // undefined. useMemo ensures the reference is stable when data is present,
  // preventing useCorrectionAudio's useEffect from tearing down/recreating
  // wavesurfer on every incidental page re-render.
  const segments = useMemo(() => rawSegments, [rawSegments]);

  const audioPanelRef = useRef<CorrectionAudioPanelHandle | null>(null);
  const searchInputRef = useRef<HTMLInputElement | null>(null);
  const updateM = useUpdateSegmentMutation(sessionId);

  useCorrectionShortcuts({
    segments,
    onPlayToggle: () => audioPanelRef.current?.playToggle(),
    onSave: () => {
      const state = useCorrectionStore.getState();
      const focusedId = state.focusedSegmentId;
      if (focusedId == null) return;
      const draft = state.draftMap.get(focusedId);
      if (!draft) return;
      updateM.mutate({
        segmentId: focusedId,
        corrected_text: draft.text,
        expected_version: draft.expectedVersion,
      });
    },
    onNextAndSave: () => {
      const state = useCorrectionStore.getState();
      const focusedId = state.focusedSegmentId;
      // Save current focused segment's draft
      if (focusedId != null) {
        const draft = state.draftMap.get(focusedId);
        if (draft) {
          updateM.mutate({
            segmentId: focusedId,
            corrected_text: draft.text,
            expected_version: draft.expectedVersion,
          });
        }
      }
      // Advance focus to next segment
      const idx = segments.findIndex((s) => s.id === focusedId);
      if (idx >= 0 && idx < segments.length - 1) {
        state.setFocused(segments[idx + 1].id);
      }
    },
    onFocusSearch: () => searchInputRef.current?.focus(),
  });

  if (!token) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="p-6">尚未登入</p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="p-6">載入校正工作台中…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="p-6 text-red-500">載入失敗：{(error as Error).message}</p>
      </div>
    );
  }

  if (!session) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="p-6">工作階段不存在</p>
      </div>
    );
  }

  return (
    <CorrectionLayout
      audioPanel={<CorrectionAudioPanel ref={audioPanelRef} session={session} segments={segments} />}
      listPanel={<SegmentList segments={segments} searchInputRef={searchInputRef} />}
      editorPanel={<SegmentEditorCardList segments={segments} />}
      toolbar={<CorrectionToolbar sessionId={sessionId} />}
    />
  );
}
