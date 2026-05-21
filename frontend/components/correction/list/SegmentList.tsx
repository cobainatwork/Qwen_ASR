'use client';

import type { CorrectionSegment } from '@/lib/api/correction';

export interface SegmentListProps {
  segments: CorrectionSegment[];
  /** Index of currently focused segment */
  activeIndex?: number;
  onSelect?: (segmentIndex: number) => void;
}

export function SegmentList(_props: SegmentListProps) {
  return <div>段落清單（待實作）</div>;
}
