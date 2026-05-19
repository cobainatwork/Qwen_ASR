'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';

import { useAuth } from '@/components/auth/useAuth';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { ApiClient, ApiError } from '@/lib/api/client';
import type { TranscribeData, YoutubeDownloadData } from '@/lib/api/types';

const POLL_INTERVAL_MS = 3000;

interface Props {
  onTranscribed: (data: TranscribeData) => void;
}

const isActiveStatus = (s: string) => s === 'pending' || s === 'downloading';

export function YoutubeDownloader({ onTranscribed }: Props) {
  const { token } = useAuth();
  const [url, setUrl] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [transcribingId, setTranscribingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [downloads, setDownloads] = useState<YoutubeDownloadData[]>([]);

  const client = useMemo(
    () => (token ? new ApiClient({ getToken: () => token }) : null),
    [token],
  );

  const refresh = useCallback(async () => {
    if (!client) return;
    try {
      const list = await client.listYoutubeDownloads({ limit: 20 });
      setDownloads(list);
    } catch (err) {
      // 靜默失敗（poll 不打擾使用者），僅在 console 留痕
      if (err instanceof ApiError) {
        console.warn('[youtube] list 失敗', err.code, err.message);
      }
    }
  }, [client]);

  // 初次載入 + 條件式 polling（有 pending/downloading 時才繼續 poll）
  useEffect(() => {
    if (!token) return;
    refresh();
    const id = setInterval(() => {
      setDownloads((prev) => {
        if (prev.some((d) => isActiveStatus(d.status))) refresh();
        return prev;
      });
    }, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [token, refresh]);

  const submit = async () => {
    if (!url.trim() || !client) return;
    setSubmitting(true);
    setError(null);
    try {
      await client.youtubeDownload(url.trim());
      setUrl('');
      await refresh();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`${err.code}: ${err.message}`);
      } else {
        setError(err instanceof Error ? err.message : '未知錯誤');
      }
    } finally {
      setSubmitting(false);
    }
  };

  const transcribe = async (audioFileId: number) => {
    if (!client) return;
    setTranscribingId(audioFileId);
    setError(null);
    try {
      const data = await client.transcribeStored(audioFileId);
      onTranscribed(data);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`${err.code}: ${err.message}`);
      } else {
        setError(err instanceof Error ? err.message : '未知錯誤');
      }
    } finally {
      setTranscribingId(null);
    }
  };

  if (!token) {
    return (
      <Card>
        <p>請先在「金鑰」頁設定 API token。</p>
      </Card>
    );
  }

  return (
    <Card>
      <h2 className="text-lg font-semibold mb-4">YouTube 音檔下載</h2>
      <div className="flex gap-2 mb-4">
        <Input
          aria-label="YouTube URL"
          placeholder="https://www.youtube.com/watch?v=..."
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          className="flex-1"
        />
        <Button onClick={submit} disabled={!url.trim() || submitting}>
          {submitting ? '送出中...' : '下載'}
        </Button>
      </div>
      {error && <p className="mb-4 text-red-500 text-sm">{error}</p>}

      {downloads.length === 0 ? (
        <p className="text-sm text-foreground/60">尚無下載紀錄</p>
      ) : (
        <ul className="divide-y divide-white/20">
          {downloads.map((d) => (
            <li key={d.id} className="py-3 flex items-center justify-between gap-4">
              <div className="min-w-0 flex-1">
                <p className="font-medium truncate" title={d.url}>
                  {d.video_title || d.url}
                </p>
                <p className="text-xs text-foreground/60">
                  狀態：<StatusLabel status={d.status} />
                  {d.duration_sec && <> ・ {d.duration_sec.toFixed(1)} 秒</>}
                  {d.file_size && <> ・ {(d.file_size / 1024 / 1024).toFixed(1)} MB</>}
                </p>
                {d.error_message && (
                  <p className="text-xs text-red-500 mt-1">{d.error_message}</p>
                )}
              </div>
              <Button
                onClick={() => d.audio_file_id && transcribe(d.audio_file_id)}
                disabled={
                  d.status !== 'completed' ||
                  d.audio_file_id === null ||
                  transcribingId === d.audio_file_id
                }
              >
                {transcribingId === d.audio_file_id ? '辨識中...' : '辨識'}
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function StatusLabel({ status }: { status: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    pending: { label: '待下載', cls: 'text-foreground/60' },
    downloading: { label: '下載中', cls: 'text-blue-500' },
    completed: { label: '已完成', cls: 'text-green-600' },
    failed: { label: '失敗', cls: 'text-red-500' },
  };
  const entry = map[status] ?? { label: status, cls: 'text-foreground/60' };
  return <span className={entry.cls}>{entry.label}</span>;
}
