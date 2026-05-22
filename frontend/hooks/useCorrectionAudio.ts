'use client';

import { useCallback, useContext, useEffect, useRef, useState, type RefObject } from 'react';
import WaveSurfer from 'wavesurfer.js';
import RegionsPlugin from 'wavesurfer.js/dist/plugins/regions';
import { AuthContext } from '@/components/auth/AuthProvider';
import { useCorrectionStore } from '@/stores/correctionStore';
import type { CorrectionSegment } from '@/lib/api/correction';

interface Options {
  audioUrl: string | null;   // e.g. "/api/v1/audio/{id}/stream"
  containerRef: RefObject<HTMLDivElement | null>;
  segments: CorrectionSegment[];
}

export function useCorrectionAudio({ audioUrl, containerRef, segments }: Options) {
  const { token } = useContext(AuthContext);
  const wsRef = useRef<WaveSurfer | null>(null);
  const regionsRef = useRef<ReturnType<typeof RegionsPlugin.create> | null>(null);
  const blobUrlRef = useRef<string | null>(null);
  // Expose isPlaying from wavesurfer events — avoids stale local state in the panel.
  const [isPlaying, setIsPlaying] = useState(false);
  // Throttle audioprocess setTime logging to avoid console spam (every 5th call).
  const setTimeCallCountRef = useRef(0);

  useEffect(() => {
    if (!audioUrl || !containerRef.current || !token) return;
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

    // Sync isPlaying from wavesurfer's authoritative play state.
    ws.on('play', () => {
      console.log('[CorrAudio] event:play', { t: ws.getCurrentTime() });
      if (!cancelled) setIsPlaying(true);
    });
    ws.on('pause', () => {
      console.log('[CorrAudio] event:pause', { t: ws.getCurrentTime() });
      if (!cancelled) setIsPlaying(false);
    });
    ws.on('finish', () => {
      console.log('[CorrAudio] event:finish');
      if (!cancelled) setIsPlaying(false);
    });
    ws.on('error', (err) => {
      console.error('[CorrAudio] event:error', err);
    });

    ws.on('ready', () => {
      console.log('[CorrAudio] event:ready', { duration: ws.getDuration() });
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
        if (t >= loopRange.end) {
          setTimeCallCountRef.current += 1;
          if (setTimeCallCountRef.current % 5 === 1) {
            console.log('[CorrAudio] segment loop seek (range)', {
              callCount: setTimeCallCountRef.current,
              from: t.toFixed(3),
              to: loopRange.start.toFixed(3),
            });
          }
          ws.setTime(loopRange.start);
        }
      } else if (loopMode === 'segment' && focusedSegmentId != null) {
        const seg = segments.find((s) => s.id === focusedSegmentId);
        if (seg && t >= seg.end_sec) {
          setTimeCallCountRef.current += 1;
          if (setTimeCallCountRef.current % 5 === 1) {
            console.log('[CorrAudio] segment loop seek (segment)', {
              callCount: setTimeCallCountRef.current,
              from: t.toFixed(3),
              to: seg.start_sec.toFixed(3),
              segId: seg.id,
            });
          }
          ws.setTime(seg.start_sec);
        }
      }
    });

    // Browser <audio> elements cannot attach custom HTTP headers, so
    // ws.load(url) directly would hit 401 on the Bearer-auth endpoint.
    // Fix: fetch the audio with Authorization header, create an object URL
    // from the blob, then feed that to wavesurfer.
    (async () => {
      try {
        const r = await fetch(audioUrl, {
          headers: { Authorization: `Bearer ${token}` },
        });
        console.log('[CorrAudio] fetch result', {
          status: r.status,
          contentType: r.headers.get('content-type'),
          contentLength: r.headers.get('content-length'),
        });
        if (!r.ok) throw new Error(`audio fetch failed: ${r.status}`);
        const blob = await r.blob();
        console.log('[CorrAudio] blob created', { size: blob.size, type: blob.type });
        if (cancelled) return;
        const blobUrl = URL.createObjectURL(blob);
        blobUrlRef.current = blobUrl;
        await ws.load(blobUrl);
        console.log('[CorrAudio] ws.load completed');
      } catch (e) {
        if (!cancelled) {
          console.error('[CorrAudio] load failed', e);
          wsRef.current = null;
        }
      }
    })();

    return () => {
      cancelled = true;
      ws.destroy();
      wsRef.current = null;
      regionsRef.current = null;
      setIsPlaying(false);
      if (blobUrlRef.current) {
        URL.revokeObjectURL(blobUrlRef.current);
        blobUrlRef.current = null;
      }
    };
  }, [audioUrl, containerRef, segments, token]);

  // All returned functions are wrapped in useCallback so their references remain
  // stable across renders. Without this, any Zustand subscriber that causes a
  // re-render (e.g. playbackTime updates via audioprocess) would produce new
  // function refs, which would re-trigger useEffect deps in the consuming
  // component and call ws.setTime() every frame — sticking playback at the
  // segment start.
  const play = useCallback(() => {
    console.log('[CorrAudio] cmd:play');
    wsRef.current?.play();
  }, []);
  const pause = useCallback(() => {
    console.log('[CorrAudio] cmd:pause');
    wsRef.current?.pause();
  }, []);
  const seek = useCallback((t: number) => {
    console.log('[CorrAudio] cmd:seek', { t: t.toFixed(3) });
    wsRef.current?.setTime(t);
  }, []);
  const setRate = useCallback((r: number) => {
    console.log('[CorrAudio] cmd:setRate', { r });
    wsRef.current?.setPlaybackRate(r, true);
  }, []);

  // seekToSegment: seek only — no zoom(). Zoom was disrupting the canvas mid-
  // playback when this was triggered automatically on every segment focus change.
  // Zoom can be re-added as a manual button if desired.
  const seekToSegment = useCallback((seg: CorrectionSegment) => {
    console.log('[CorrAudio] cmd:seekToSegment', { id: seg.id, start: seg.start_sec.toFixed(3), end: seg.end_sec.toFixed(3) });
    wsRef.current?.setTime(seg.start_sec);
  }, []);

  return { play, pause, seek, setRate, seekToSegment, isPlaying };
}
