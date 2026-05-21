'use client';

import type { CorrectionSegment } from '@/lib/api/correction';

export interface SegmentEditorCardProps {
  segment: CorrectionSegment;
  isActive?: boolean;
  onSave?: (segmentId: number, text: string, expectedVersion: number) => Promise<void>;
  onSkip?: (segmentId: number) => void;
}

export function SegmentEditorCard(_props: SegmentEditorCardProps) {
  return <div>編輯卡片（待實作）</div>;
}

export interface SegmentEditorCardListProps {
  segments: CorrectionSegment[];
  activeIndex?: number;
  onSave?: (segmentId: number, text: string, expectedVersion: number) => Promise<void>;
  onSkip?: (segmentId: number) => void;
}

export function SegmentEditorCardList(_props: SegmentEditorCardListProps) {
  return <div>編輯區（待實作）</div>;
}
