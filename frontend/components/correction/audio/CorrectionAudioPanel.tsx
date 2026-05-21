'use client';

import type { CorrectionSession, CorrectionSegment } from '@/lib/api/correction';

export interface CorrectionAudioPanelProps {
  session: CorrectionSession;
  segments: CorrectionSegment[];
  /** Currently active segment index (0-based); used to seek audio in M2.2 */
  activeSegmentIndex?: number;
  onSegmentSeek?: (segmentIndex: number) => void;
}

export function CorrectionAudioPanel(_props: CorrectionAudioPanelProps) {
  return <div>音訊區（待實作）</div>;
}
