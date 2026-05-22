'use client';

import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef } from 'react';
import { Pause, Play } from 'lucide-react';

import { useCorrectionAudio } from '@/hooks/useCorrectionAudio';
import { useCorrectionStore } from '@/stores/correctionStore';
import { formatTimestamp } from '@/lib/format/time';
import type { CorrectionSegment, CorrectionSession } from '@/lib/api/correction';

export interface CorrectionAudioPanelProps {
  session: CorrectionSession;
  segments: CorrectionSegment[];
  /** Currently active segment index (0-based); used to seek audio in M2.2 */
  activeSegmentIndex?: number;
  onSegmentSeek?: (segmentIndex: number) => void;
}

export interface CorrectionAudioPanelHandle {
  playToggle: () => void;
}

const RATES = [0.5, 0.75, 1, 1.25, 1.5, 2] as const;

export const CorrectionAudioPanel = forwardRef<
  CorrectionAudioPanelHandle,
  CorrectionAudioPanelProps
>(function CorrectionAudioPanel({ session, segments }, ref) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  const audioUrl = useMemo(() => {
    if (!session.audio_file_id) return null;
    return `/api/v1/audio/${session.audio_file_id}/stream`;
  }, [session.audio_file_id]);

  // isPlaying is sourced from the hook (synced via ws 'play'/'pause'/'finish' events)
  // rather than local state to avoid divergence when wavesurfer stops unexpectedly.
  const { play, pause, setRate, seekToSegment, isPlaying } = useCorrectionAudio({
    audioUrl,
    containerRef,
    segments,
  });

  // useImperativeHandle uses stable refs from the hook — safe to depend on them.
  useImperativeHandle(ref, () => ({
    playToggle: () => {
      if (isPlaying) pause();
      else play();
    },
  }), [isPlaying, play, pause]);

  const playbackRate = useCorrectionStore((s) => s.playbackRate);
  const playbackTime = useCorrectionStore((s) => s.playbackTime);
  const setPlaybackRate = useCorrectionStore((s) => s.setPlaybackRate);
  const focusedSegmentId = useCorrectionStore((s) => s.focusedSegmentId);

  // Spec §4.3 line 1088: clicking a segment → seek to start → auto-play.
  // seekToSegment and play are stable useCallback refs from useCorrectionAudio,
  // so this effect only fires when focusedSegmentId actually changes — not on
  // every audioprocess-driven re-render.
  useEffect(() => {
    if (focusedSegmentId == null) return;
    const seg = segments.find((s) => s.id === focusedSegmentId);
    if (!seg) return;
    seekToSegment(seg);
    play();
  }, [focusedSegmentId, segments, seekToSegment, play]);

  const focusedSeg = segments.find((s) => s.id === focusedSegmentId);
  const correctedCount = segments.filter((s) => s.corrected_text && !s.is_skipped).length;
  const skippedCount = segments.filter((s) => s.is_skipped).length;
  const uncorrectedCount = segments.length - correctedCount - skippedCount;

  return (
    <div className="flex flex-col h-full p-2 gap-2 text-sm">
      {/* Waveform container — wavesurfer mounts here */}
      <div
        ref={containerRef}
        data-testid="waveform-container"
        className="h-[160px] flex-shrink-0 rounded border border-slate-200 bg-slate-50"
      />

      {/* Playback controls */}
      <div className="flex items-center gap-2 flex-wrap">
        <button
          type="button"
          aria-label="播放 / 暫停"
          onClick={() => { play(); }}
          className="flex items-center gap-1 px-2 py-1 rounded bg-blue-500 text-white text-xs hover:bg-blue-600 focus-visible:ring-2 focus-visible:ring-blue-400"
        >
          <Play size={13} aria-hidden="true" />
          播放
        </button>

        <button
          type="button"
          aria-label="暫停"
          onClick={() => { pause(); }}
          className="flex items-center gap-1 px-2 py-1 rounded border text-xs hover:bg-slate-100 focus-visible:ring-2 focus-visible:ring-slate-400"
        >
          <Pause size={13} aria-hidden="true" />
          暫停
        </button>

        <span className="flex items-center gap-1 text-xs">
          <span id="audio-rate-label">速度</span>
          <select
            aria-label="播放速度"
            value={playbackRate}
            onChange={(e) => {
              const r = Number(e.target.value);
              setPlaybackRate(r);
              setRate(r);
            }}
            className="border rounded px-1 py-0.5 text-xs"
          >
            {RATES.map((r) => (
              <option key={r} value={r}>
                {r}x
              </option>
            ))}
          </select>
        </span>
      </div>

      {/* Current time + focused segment info */}
      <div className="text-xs text-slate-500">
        <span>時間：{formatTimestamp(playbackTime)}</span>
        {focusedSeg && (
          <span className="ml-2 text-slate-700">
            段落 #{focusedSeg.segment_index}
            {focusedSeg.speaker_label ? `（${focusedSeg.speaker_label}）` : ''}
          </span>
        )}
      </div>

      {/* Statistics */}
      <div className="mt-auto text-xs space-y-0.5 border-t border-slate-100 pt-1">
        <div>總段落：{segments.length}</div>
        <div>已校正：{correctedCount}</div>
        <div>未校正：{uncorrectedCount}</div>
        <div>跳過：{skippedCount}</div>
      </div>
    </div>
  );
});
