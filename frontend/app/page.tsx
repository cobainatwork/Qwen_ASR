'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';

import { AudioUploader } from '@/components/asr/AudioUploader';
import { TranscriptionResult } from '@/components/asr/TranscriptionResult';
import { AudioPlayer, type AudioPlayerHandle } from '@/components/asr/AudioPlayer';
import { TranscriptViewer } from '@/components/asr/TranscriptViewer';
import { ExportButtons } from '@/components/asr/ExportButtons';
import { CorrectionApiError, useCreateCorrectionSessionMutation } from '@/lib/api/correction';
import type { TranscribeData } from '@/lib/api/types';

const STORAGE_KEY = 'qwen-asr:last-transcribe-result';

type StoredResult = { data: TranscribeData; clientElapsedMs: number };

export default function Page() {
  const [stored, setStored] = useState<StoredResult | null>(null);
  const [isRehydrated, setIsRehydrated] = useState(false);
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const playerRef = useRef<AudioPlayerHandle | null>(null);
  const router = useRouter();
  const createSessionM = useCreateCorrectionSessionMutation();

  const audioUrl = useMemo(() => {
    if (!audioFile) return null;
    return URL.createObjectURL(audioFile);
  }, [audioFile]);

  useEffect(() => {
    return () => {
      if (audioUrl) URL.revokeObjectURL(audioUrl);
    };
  }, [audioUrl]);

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const parsed: unknown = JSON.parse(raw);
      if (
        parsed !== null &&
        typeof parsed === 'object' &&
        'data' in parsed &&
        parsed.data !== null &&
        typeof parsed.data === 'object' &&
        'text' in parsed.data &&
        'transcription_id' in parsed.data &&
        typeof (parsed.data as { transcription_id: unknown }).transcription_id === 'number' &&
        'clientElapsedMs' in parsed &&
        typeof (parsed as { clientElapsedMs: unknown }).clientElapsedMs === 'number'
      ) {
        setStored(parsed as StoredResult);
        setIsRehydrated(true);
      } else {
        sessionStorage.removeItem(STORAGE_KEY);
      }
    } catch {
      try { sessionStorage.removeItem(STORAGE_KEY); } catch { /* 配額/SecurityError 靜默 */ }
    }
  }, []);

  const handleTranscribeStart = () => {
    setStored(null);
    setIsRehydrated(false);
    try {
      sessionStorage.removeItem(STORAGE_KEY);
    } catch {/* 靜默 */}
  };

  const handleResult = (data: TranscribeData, clientElapsedMs: number) => {
    const next: StoredResult = { data, clientElapsedMs };
    setStored(next);
    setIsRehydrated(false);
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {/* 配額或 SecurityError，靜默 */}
  };

  const handleClear = () => {
    setStored(null);
    setIsRehydrated(false);
    setAudioFile(null);
    try {
      sessionStorage.removeItem(STORAGE_KEY);
    } catch {/* 靜默 */}
  };

  const handleSeekFromTranscript = (seconds: number) => {
    setCurrentTime(seconds);
    playerRef.current?.seek(seconds);
  };

  const handleEnterCorrection = async () => {
    if (!stored?.data.transcription_id) return;
    try {
      const sess = await createSessionM.mutateAsync({
        transcription_id: stored.data.transcription_id,
      });
      router.push(`/correction/${sess.id}`);
    } catch (e) {
      if (e instanceof CorrectionApiError && e.code === 'TRANSCRIPTION_NOT_FOUND') {
        try { sessionStorage.removeItem(STORAGE_KEY); } catch {/* 靜默 */}
        window.alert('此辨識紀錄已不存在（可能已被刪除）。請重新上傳音檔。');
        window.location.reload();
      } else {
        window.alert(`進入校正失敗：${(e as Error).message}`);
      }
    }
  };

  return (
    <div className="asr-page">
      <div className="asr-upload-area">
        <AudioUploader
          onResult={handleResult}
          onTranscribeStart={handleTranscribeStart}
          onFileSelected={setAudioFile}
        />
        {isRehydrated && stored && (
          <div className="mt-2 flex items-center gap-3 rounded-xl border border-amber-300/60 bg-amber-50/70 backdrop-blur-sm px-4 py-1.5 text-xs text-amber-900">
            <span aria-hidden>ⓘ</span>
            <span className="flex-1">
              此為先前紀錄（瀏覽器 sessionStorage 留存），重新上傳音檔才能播放波形。
            </span>
            <button
              type="button"
              onClick={handleClear}
              className="rounded-lg border border-amber-400/60 px-2 py-1 text-amber-900 hover:bg-amber-100/60 transition-colors cursor-pointer"
            >
              清除
            </button>
          </div>
        )}
      </div>

      <div className="asr-waveform-area">
        {audioUrl ? (
          <AudioPlayer
            ref={playerRef}
            audioUrl={audioUrl}
            speakers={stored?.data.speakers}
            onTimeUpdate={setCurrentTime}
          />
        ) : (
          <div className="h-full flex items-center justify-center text-sm text-foreground/50 italic border border-dashed border-foreground/15 rounded-xl bg-white/30 backdrop-blur-sm">
            {stored ? '重新上傳音檔以播放波形' : '上傳音檔後將顯示波形'}
          </div>
        )}
      </div>

      <div className="asr-transcript-area">
        {stored ? (
          <>
            <div className="flex items-center justify-between gap-3 px-4 py-2 border-b border-foreground/10 sticky top-0 bg-white/80 backdrop-blur-sm z-10">
              <div className="flex items-center gap-2">
                <ExportButtons data={stored.data} baseFilename={`transcription-${stored.data.transcription_id}`} />
                <button
                  type="button"
                  onClick={handleEnterCorrection}
                  disabled={createSessionM.isPending}
                  className="rounded-lg border border-accent/50 bg-accent/10 px-3 py-1.5 text-xs text-accent hover:bg-accent/20 disabled:opacity-50 transition-colors"
                >
                  {createSessionM.isPending ? '建立中...' : '進入校正工作台'}
                </button>
              </div>
              <span className="text-xs text-foreground/60 font-mono tabular-nums">
                {stored.data.duration_sec.toFixed(1)}s · {stored.data.vad_segments_count} VAD · {stored.data.model_version}
              </span>
            </div>
            <TranscriptViewer data={stored.data} currentTime={currentTime} onSeek={handleSeekFromTranscript} />
            <div className="px-4 py-3 border-t border-foreground/10">
              <TranscriptionResult data={stored.data} clientElapsedMs={stored.clientElapsedMs} />
            </div>
          </>
        ) : (
          <div className="h-full flex items-center justify-center text-sm text-foreground/50 italic">
            尚無辨識結果
          </div>
        )}
      </div>
    </div>
  );
}
