'use client';

import { useContext } from 'react';
import { useParams } from 'next/navigation';

import { AuthContext } from '@/components/auth/AuthProvider';
import { useCorrectionSession } from '@/hooks/useCorrectionSession';
import { CorrectionLayout } from '@/components/correction/CorrectionLayout';
import { CorrectionAudioPanel } from '@/components/correction/audio/CorrectionAudioPanel';
import { SegmentList } from '@/components/correction/list/SegmentList';
import { SegmentEditorCardList } from '@/components/correction/editor/SegmentEditorCard';
import { CorrectionToolbar } from '@/components/correction/CorrectionToolbar';

export default function CorrectionWorkbenchPage() {
  const { session_id } = useParams<{ session_id: string }>();
  const { token } = useContext(AuthContext);
  const sessionId = Number(session_id);

  // apiKeyId is not exposed by AuthContext in V1; hook accepts it as optional
  const { session, segments, isLoading, error } = useCorrectionSession(sessionId, undefined);

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
      audioPanel={<CorrectionAudioPanel session={session} segments={segments} />}
      listPanel={<SegmentList segments={segments} />}
      editorPanel={<SegmentEditorCardList segments={segments} />}
      toolbar={<CorrectionToolbar sessionId={sessionId} />}
    />
  );
}
