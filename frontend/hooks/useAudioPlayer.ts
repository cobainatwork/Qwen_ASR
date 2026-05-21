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

    // race guard：當 audioUrl 在前一個 load 完成前換手（使用者極快連選兩檔），
    // cleanup 先跑 destroy 舊 ws、設 cancelled=true；新 effect 重 create + load 新 url。
    // 若舊 ws 的 in-flight load 在 destroy 後仍觸發 ready/error，cancelled flag 阻止
    // 它呼叫 stale setState（adversarial review IMPORTANT #1 防禦）。
    let cancelled = false;

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
      if (cancelled) return;
      setIsReady(true);
      setDuration(ws.getDuration());
    });
    ws.on('play', () => { if (!cancelled) setIsPlaying(true); });
    ws.on('pause', () => { if (!cancelled) setIsPlaying(false); });
    ws.on('finish', () => { if (!cancelled) setIsPlaying(false); });
    ws.on('audioprocess', () => { if (!cancelled) setCurrentTime(ws.getCurrentTime()); });
    ws.on('seeking', () => { if (!cancelled) setCurrentTime(ws.getCurrentTime()); });

    ws.load(audioUrl).catch(() => {
      if (!cancelled) setIsReady(false);
    });

    return () => {
      cancelled = true;
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
