'use client';

import { useEffect } from 'react';
import { useCorrectionStore } from '@/stores/correctionStore';
import type { CorrectionSegment } from '@/lib/api/correction';

interface Options {
  segments: CorrectionSegment[];
  onPlayToggle: () => void;
  onSave: () => void;
  onNextAndSave: () => void;
  onFocusSearch: () => void;
}

export function useCorrectionShortcuts({
  segments,
  onPlayToggle,
  onSave,
  onNextAndSave,
  onFocusSearch,
}: Options) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName;
      const inTextField = tag === 'INPUT' || tag === 'TEXTAREA';

      // Ctrl+S: force save — preventDefault even when textarea is focused
      if (e.ctrlKey && e.code === 'KeyS') {
        e.preventDefault();
        onSave();
        return;
      }
      // Ctrl+Enter: next segment + autosave
      if (e.ctrlKey && e.code === 'Enter') {
        e.preventDefault();
        onNextAndSave();
        return;
      }
      // Ctrl+F: focus search box
      if (e.ctrlKey && e.code === 'KeyF') {
        e.preventDefault();
        onFocusSearch();
        return;
      }
      // Escape: blur textarea OR exit focusMode
      if (e.code === 'Escape') {
        if (inTextField) {
          (e.target as HTMLElement).blur();
        } else if (useCorrectionStore.getState().focusMode) {
          useCorrectionStore.getState().toggleFocusMode();
        }
        return;
      }

      // The remaining shortcuts are skipped when a text field is focused.
      if (inTextField) return;

      const { focusedSegmentId, setFocused } = useCorrectionStore.getState();
      const idx = segments.findIndex((s) => s.id === focusedSegmentId);

      if (e.code === 'Space') {
        e.preventDefault();
        onPlayToggle();
      } else if (e.code === 'ArrowLeft') {
        e.preventDefault();
        const prevSeg = segments[Math.max(0, idx - 1)];
        if (prevSeg) setFocused(prevSeg.id);
      } else if (e.code === 'ArrowRight') {
        e.preventDefault();
        const nextSeg = segments[Math.min(segments.length - 1, idx + 1)];
        if (nextSeg) setFocused(nextSeg.id);
      } else if (e.code === 'Home') {
        e.preventDefault();
        if (segments[0]) setFocused(segments[0].id);
      } else if (e.code === 'End') {
        e.preventDefault();
        if (segments.length > 0) setFocused(segments[segments.length - 1].id);
      }
    };

    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [segments, onPlayToggle, onSave, onNextAndSave, onFocusSearch]);
}
