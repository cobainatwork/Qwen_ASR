'use client';

import { type RefObject, useMemo, useRef } from 'react';
import { useCorrectionStore } from '@/stores/correctionStore';
import { useVirtualList } from '@/hooks/useVirtualList';
import { SegmentListItem } from './SegmentListItem';
import { SegmentListSearch } from './SegmentListSearch';
import { SegmentListStats } from './SegmentListStats';
import type { CorrectionSegment } from '@/lib/api/correction';

export interface SegmentListProps {
  segments: CorrectionSegment[];
  /** Forwarded to SegmentListSearch input for Ctrl+F focus shortcut */
  searchInputRef?: RefObject<HTMLInputElement>;
}

export function SegmentList({ segments, searchInputRef }: SegmentListProps) {
  const scrollRef = useRef<HTMLUListElement | null>(null);
  const q = useCorrectionStore((s) => s.searchQuery);
  const fs = useCorrectionStore((s) => s.filterSpeaker);
  const ft = useCorrectionStore((s) => s.filterStatus);

  const speakers = useMemo(() => {
    const set = new Set<string>();
    segments.forEach((s) => {
      if (s.speaker_label) set.add(s.speaker_label);
    });
    return Array.from(set).sort();
  }, [segments]);

  const filtered = useMemo(() => {
    return segments.filter((s) => {
      if (q && !(s.original_text.includes(q) || (s.corrected_text ?? '').includes(q)))
        return false;
      if (fs && s.speaker_label !== fs) return false;
      if (ft === 'corrected' && (!s.corrected_text || s.is_skipped)) return false;
      if (ft === 'uncorrected' && (s.corrected_text || s.is_skipped)) return false;
      if (ft === 'skipped' && !s.is_skipped) return false;
      return true;
    });
  }, [segments, q, fs, ft]);

  const { isVirtual, virtualizer } = useVirtualList({
    items: filtered,
    scrollRef,
    estimateSize: () => 44,
    threshold: 100,
    overscan: 5,
  });

  return (
    <div className="flex flex-col h-full">
      <SegmentListSearch speakers={speakers} inputRef={searchInputRef} />
      <ul ref={scrollRef as React.RefObject<HTMLUListElement>} className="flex-1 overflow-y-auto">
        {!isVirtual && filtered.map((s) => <SegmentListItem key={s.id} segment={s} />)}
        {isVirtual && (
          <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
            {virtualizer.getVirtualItems().map((vi) => {
              const seg = filtered[vi.index];
              return (
                <div
                  key={seg.id}
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    right: 0,
                    transform: `translateY(${vi.start}px)`,
                  }}
                >
                  <SegmentListItem segment={seg} />
                </div>
              );
            })}
          </div>
        )}
      </ul>
      <SegmentListStats segments={segments} />
    </div>
  );
}
