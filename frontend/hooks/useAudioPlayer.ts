'use client';

import { useEffect, useRef, useState, useCallback, type RefObject } from 'react';
import WaveSurfer from 'wavesurfer.js';

interface Options {
  audioUrl: string | null;
  containerRef: RefObject<HTMLDivElement | null>;
}

interface ReturnShape {
  isReady: boolean;
  isPlaying: boolean;
  currentTime: number;
  duration: number;
  play: () => void;
  pause: () => void;
  toggle: () => void;
  seek: (seconds: number) => void;
  setRate: (rate: number) => void;
  setVolume: (v: number) => void;
}

export function useAudioPlayer({ audioUrl, containerRef }: Options): ReturnShape {
  const wsRef = useRef<WaveSurfer | null>(null);
  const [isReady, setIsReady] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);

  useEffect(() => {
    if (!audioUrl || !containerRef.current) return;

    const ws = WaveSurfer.create({
      container: containerRef.current,
      waveColor: '#94a3b8',
      progressColor: '#3b82f6',
      cursorColor: '#1e293b',
      height: 100,
      barWidth: 2,
      barGap: 1,
    });
    wsRef.current = ws;

    ws.on('ready', () => {
      setIsReady(true);
      setDuration(ws.getDuration());
    });
    ws.on('play', () => setIsPlaying(true));
    ws.on('pause', () => setIsPlaying(false));
    ws.on('finish', () => setIsPlaying(false));
    ws.on('audioprocess', () => setCurrentTime(ws.getCurrentTime()));
    ws.on('seeking', () => setCurrentTime(ws.getCurrentTime()));

    ws.load(audioUrl).catch(() => {
      setIsReady(false);
    });

    return () => {
      ws.destroy();
      wsRef.current = null;
      setIsReady(false);
      setIsPlaying(false);
      setCurrentTime(0);
      setDuration(0);
    };
  }, [audioUrl, containerRef]);

  const play = useCallback(() => { wsRef.current?.play(); }, []);
  const pause = useCallback(() => { wsRef.current?.pause(); }, []);
  const toggle = useCallback(() => {
    if (!wsRef.current) return;
    if (wsRef.current.isPlaying()) wsRef.current.pause();
    else wsRef.current.play();
  }, []);
  const seek = useCallback((seconds: number) => {
    wsRef.current?.setTime(seconds);
  }, []);
  const setRate = useCallback((rate: number) => {
    wsRef.current?.setPlaybackRate(rate, true);
  }, []);
  const setVolume = useCallback((v: number) => {
    wsRef.current?.setVolume(Math.max(0, Math.min(1, v)));
  }, []);

  return { isReady, isPlaying, currentTime, duration, play, pause, toggle, seek, setRate, setVolume };
}
