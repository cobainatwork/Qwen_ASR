'use client';

import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react';
import { Play, Pause, Volume2, VolumeX } from 'lucide-react';

import { useAudioPlayer } from '@/hooks/useAudioPlayer';
import { formatTimestamp } from '@/lib/format/time';
import type { SpeakerTurn } from '@/lib/api/types';

interface Props {
  audioUrl: string | null;
  speakers: SpeakerTurn[] | null | undefined;
  onTimeUpdate?: (currentTimeSec: number) => void;
}

export interface AudioPlayerHandle {
  seek: (seconds: number) => void;
}

const RATES = [0.5, 0.75, 1, 1.25, 1.5, 2] as const;

export const AudioPlayer = forwardRef<AudioPlayerHandle, Props>(function AudioPlayer(
  { audioUrl, speakers, onTimeUpdate },
  ref,
) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const { isReady, isPlaying, currentTime, duration, toggle, seek, setRate, setVolume } =
    useAudioPlayer({ audioUrl, containerRef });
  const [rate, setRateState] = useState(1);
  const [volume, setVolumeState] = useState(1);
  const [muted, setMuted] = useState(false);

  useImperativeHandle(ref, () => ({ seek }), [seek]);

  useEffect(() => {
    onTimeUpdate?.(currentTime);
  }, [currentTime, onTimeUpdate]);

  useEffect(() => {
    if (!isReady) return;
    const handler = (e: KeyboardEvent) => {
      // Disable shortcuts when focus is inside an editable field
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA') return;
      if (e.code === 'Space') {
        e.preventDefault();
        toggle();
      } else if (e.code === 'ArrowLeft') {
        e.preventDefault();
        seek(Math.max(0, currentTime - 5));
      } else if (e.code === 'ArrowRight') {
        e.preventDefault();
        seek(Math.min(duration, currentTime + 5));
      } else if (e.code === 'ArrowUp') {
        e.preventDefault();
        const next = Math.min(1, volume + 0.1);
        setVolumeState(next);
        setVolume(next);
      } else if (e.code === 'ArrowDown') {
        e.preventDefault();
        const next = Math.max(0, volume - 0.1);
        setVolumeState(next);
        setVolume(next);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [isReady, currentTime, duration, volume, toggle, seek, setVolume]);

  const handleRateChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const r = Number(e.target.value);
    setRateState(r);
    setRate(r);
  };

  const handleVolumeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = Number(e.target.value);
    setVolumeState(v);
    setVolume(muted ? 0 : v);
  };

  const toggleMute = () => {
    const next = !muted;
    setMuted(next);
    setVolume(next ? 0 : volume);
  };

  return (
    <div className="flex flex-col h-full px-4 py-3 bg-white/40 backdrop-blur-sm border border-foreground/10 rounded-xl">
      <div ref={containerRef} className="flex-1 min-h-0" data-testid="waveform-container" />
      <div className="flex items-center gap-3 mt-2 text-sm">
        <button
          type="button"
          onClick={toggle}
          disabled={!isReady}
          aria-label={isPlaying ? '暫停' : '播放'}
          className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-blue-500 text-white disabled:opacity-40 disabled:cursor-not-allowed hover:bg-blue-600 transition-colors cursor-pointer"
        >
          {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 ml-0.5" />}
        </button>
        <span className="font-mono text-xs text-foreground/70 tabular-nums">
          {formatTimestamp(currentTime)} / {formatTimestamp(duration)}
        </span>
        <label className="flex items-center gap-1 text-xs">
          <span className="text-foreground/60">速度</span>
          <select
            aria-label="播放速度"
            value={rate}
            onChange={handleRateChange}
            className="rounded border border-foreground/15 bg-white/70 px-1 py-0.5 text-xs"
          >
            {RATES.map((r) => (
              <option key={r} value={r}>
                {r}x
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={toggleMute}
          aria-label={muted ? '取消靜音' : '靜音'}
          className="text-foreground/70 hover:text-foreground"
        >
          {muted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
        </button>
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={muted ? 0 : volume}
          onChange={handleVolumeChange}
          aria-label="音量"
          className="w-24"
        />
        {speakers && speakers.length > 0 && (
          <span className="ml-auto text-xs text-foreground/50">{speakers.length} 位語者</span>
        )}
      </div>
    </div>
  );
});
