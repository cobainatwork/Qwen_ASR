'use client';

import type { CorrectionSegment } from '@/lib/api/correction';

export function SegmentListStats({ segments }: { segments: CorrectionSegment[] }) {
  const total = segments.length;
  const corrected = segments.filter((s) => s.corrected_text && !s.is_skipped).length;
  const pct = total === 0 ? 0 : Math.round((corrected / total) * 100);

  return (
    <div className="p-2 border-t text-xs">
      <div>已校正 {pct}%</div>
      <div className="h-1 bg-gray-200 rounded overflow-hidden">
        <div className="h-full bg-blue-500" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
