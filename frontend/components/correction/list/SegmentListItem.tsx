'use client';

import { Check, AlertCircle, SkipForward, Pencil } from 'lucide-react';
import { useCorrectionStore } from '@/stores/correctionStore';
import { formatTimestamp } from '@/lib/format/time';
import type { CorrectionSegment } from '@/lib/api/correction';

export function SegmentListItem({ segment }: { segment: CorrectionSegment }) {
  const focusedId = useCorrectionStore((s) => s.focusedSegmentId);
  const saveState = useCorrectionStore((s) => s.saveStates.get(segment.id));
  const setFocused = useCorrectionStore((s) => s.setFocused);
  const isFocused = focusedId === segment.id;

  const StatusIcon = () => {
    if (segment.is_skipped) return <SkipForward size={12} aria-label="已跳過" />;
    if (saveState === 'saving' || saveState === 'unsaved')
      return <Pencil size={12} aria-label="編輯中" />;
    if (segment.corrected_text)
      return <Check size={12} aria-label="已校正" className="text-green-600" />;
    return <AlertCircle size={12} aria-label="未校正" className="text-amber-500" />;
  };

  return (
    <li
      role="listitem"
      tabIndex={0}
      onClick={() => setFocused(segment.id)}
      className={`px-2 py-1 cursor-pointer text-xs ${isFocused ? 'bg-blue-100' : 'hover:bg-gray-50'}`}
      aria-current={isFocused ? 'true' : undefined}
    >
      <div className="flex items-center justify-between">
        <span>
          <span>#{segment.segment_index}</span>
          <span className="ml-1 text-foreground/70">{segment.speaker_label ?? '—'}</span>
        </span>
        <StatusIcon />
      </div>
      <div className="text-foreground/60 font-mono">
        {formatTimestamp(segment.start_sec)} – {formatTimestamp(segment.end_sec)}
      </div>
    </li>
  );
}
