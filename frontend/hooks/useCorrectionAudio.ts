'use client';

import { useEffect, useRef, type RefObject } from 'react';
import WaveSurfer from 'wavesurfer.js';
import RegionsPlugin from 'wavesurfer.js/dist/plugins/regions';
import { useCorrectionStore } from '@/stores/correctionStore';
import type { CorrectionSegment } from '@/lib/api/correction';

interface Options {
  audioUrl: string | null;
  containerRef: RefObject<HTMLDivElement | null>;
  segments: CorrectionSegment[];
}

export function useCorrectionAudio({ audioUrl, containerRef, segments }: Options) {
  const wsRef = useRef<WaveSurfer | null>(null);
  const regionsRef = useRef<ReturnType<typeof RegionsPlugin.create> | null>(null);

  useEffect(() => {
    if (!audioUrl || !containerRef.current) return;
    let cancelled = false;

    const regions = RegionsPlugin.create();
    const ws = WaveSurfer.create({
      container: containerRef.current,
      waveColor: '#94a3b8',
      progressColor: '#3b82f6',
      cursorColor: '#1e293b',
      height: 100,
      barWidth: 2,
      barGap: 1,
      plugins: [regions],
    });
    wsRef.current = ws;
    regionsRef.current = regions;

    ws.on('ready', () => {
      if (cancelled) return;
      segments.forEach((seg, idx) => {
        regions.addRegion({
          start: seg.start_sec,
          end: seg.end_sec,
          content: seg.speaker_label ?? `#${idx}`,
          color: seg.speaker_label
            ? `hsla(${(seg.speaker_label.charCodeAt(0) * 30) % 360}, 60%, 60%, 0.2)`
            : 'hsla(0, 0%, 60%, 0.1)',
          drag: false,
          resize: false,
        });
      });
    });

    ws.on('audioprocess', () => {
      if (cancelled) return;
      const t = ws.getCurrentTime();
      useCorrectionStore.getState().setPlayback(t);

      const { loopMode, loopRange, focusedSegmentId } = useCorrectionStore.getState();
      if (loopMode === 'range' && loopRange) {
        if (t >= loopRange.end) ws.setTime(loopRange.start);
      } else if (loopMode === 'segment' && focusedSegmentId != null) {
        const seg = segments.find((s) => s.id === focusedSegmentId);
        if (seg && t >= seg.end_sec) ws.setTime(seg.start_sec);
      }
    });

    ws.load(audioUrl).catch(() => {
      if (!cancelled) wsRef.current = null;
    });

    return () => {
      cancelled = true;
      ws.destroy();
      wsRef.current = null;
      regionsRef.current = null;
    };
  }, [audioUrl, containerRef, segments]);

  return {
    play: () => wsRef.current?.play(),
    pause: () => wsRef.current?.pause(),
    seek: (t: number) => wsRef.current?.setTime(t),
    setRate: (r: number) => wsRef.current?.setPlaybackRate(r, true),
    zoomToSegment: (seg: CorrectionSegment) => {
      if (!wsRef.current) return;
      const duration = wsRef.current.getDuration();
      if (duration > 0) {
        const ratio = (seg.end_sec - seg.start_sec) / duration;
        wsRef.current.zoom(Math.min(200, Math.max(50, 100 / ratio)));
      }
      wsRef.current.setTime(seg.start_sec);
    },
  };
}
