'use client';

import { useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { useParams } from 'next/navigation';

import { AuthContext } from '@/components/auth/AuthProvider';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { SegmentEditor } from '@/components/correction/SegmentEditor';
import {
  CorrectionApi,
  CorrectionApiError,
  type CorrectionSegment,
  type CorrectionSession,
} from '@/lib/api/correction';

// ─── 頁面元件 ─────────────────────────────────────────────────────────────────

export default function CorrectionWorkbenchPage() {
  const { session_id } = useParams<{ session_id: string }>();
  const { token } = useContext(AuthContext);

  // useMemo 穩定 api 實例，避免 token 未變時重複建立破壞 useCallback deps
  const api = useMemo(
    () => new CorrectionApi({ getToken: () => token }),
    [token],
  );

  const sessionId = Number(session_id);

  // ─── 工作階段與片段狀態 ─────────────────────────────────────────────────────

  const [session, setSession] = useState<CorrectionSession | null>(null);
  const [segments, setSegments] = useState<CorrectionSegment[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!token) {
      setLoadError('尚未登入，請先設定 API 金鑰');
      setLoading(false);
      return;
    }
    setLoading(true);
    setLoadError(null);
    try {
      const [sess, segs] = await Promise.all([
        api.getSession(sessionId),
        api.listSegments(sessionId),
      ]);
      setSession(sess);
      setSegments(segs);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : '載入失敗');
    } finally {
      setLoading(false);
    }
  }, [api, sessionId, token]);

  useEffect(() => {
    reload();
  }, [reload]);

  // ─── 片段儲存（含 optimistic locking 衝突處理） ───────────────────────────

  async function handleSaveSegment(
    segmentId: number,
    text: string,
    expectedVersion: number,
  ) {
    // Optimistic update：先以本地版本替換畫面
    const updated = await api.updateSegment(sessionId, segmentId, {
      corrected_text: text,
      expected_version: expectedVersion,
    });
    // 以最新版本取代本地狀態，避免二次衝突
    setSegments((prev) =>
      prev.map((seg) => (seg.id === segmentId ? updated : seg)),
    );
    // 與後端同步確保 version 正確（避免下次儲存 version 不一致）
    await reload();
  }

  // ─── 匯出至資料集狀態 ─────────────────────────────────────────────────────

  const [datasetId, setDatasetId] = useState('');
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exportResult, setExportResult] = useState<{
    insertedCount: number;
    datasetId: number;
  } | null>(null);

  async function handleExport() {
    const parsedId = Number(datasetId);
    if (!datasetId.trim() || isNaN(parsedId) || parsedId <= 0) return;
    setExporting(true);
    setExportError(null);
    setExportResult(null);
    try {
      const result = await api.exportToDataset(sessionId, {
        dataset_id: parsedId,
      });
      setExportResult({
        insertedCount: result.inserted_count,
        datasetId: result.dataset_id,
      });
    } catch (err) {
      if (err instanceof CorrectionApiError) {
        setExportError(`${err.code}：${err.message}`);
      } else {
        setExportError(err instanceof Error ? err.message : '匯出失敗');
      }
    } finally {
      setExporting(false);
    }
  }

  // ─── 渲染 ────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <p className="text-foreground/60">載入校正工作台中…</p>
      </main>
    );
  }

  if (loadError) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <Card className="max-w-md w-full">
          <p className="text-red-500 text-sm">{loadError}</p>
          <Button onClick={reload} className="mt-4">
            重新載入
          </Button>
        </Card>
      </main>
    );
  }

  return (
    <main className="min-h-screen p-6 max-w-4xl mx-auto space-y-6">
      {/* 工作階段標頭 */}
      <Card>
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-xl font-semibold text-foreground">
              校正工作台
            </h1>
            <h2 className="text-base font-medium text-foreground/80 mt-0.5">
              {session?.name}
            </h2>
            <p className="text-sm text-foreground/60 mt-1">
              工作階段 #{session?.id}（轉譯 #{session?.transcription_id}）
            </p>
          </div>
          <span
            className={`px-3 py-1 rounded-full text-xs font-medium ${
              session?.status === 'completed' || session?.status === 'exported'
                ? 'bg-green-100 text-green-700'
                : 'bg-accent/10 text-accent'
            }`}
          >
            {session?.status === 'pending' && '待校正'}
            {session?.status === 'in_progress' && '校正中'}
            {session?.status === 'completed' && '已完成'}
            {session?.status === 'exported' && '已匯出'}
            {session?.status !== 'pending' &&
              session?.status !== 'in_progress' &&
              session?.status !== 'completed' &&
              session?.status !== 'exported' &&
              session?.status}
          </span>
        </div>
      </Card>

      {/* 片段列表 */}
      <section className="space-y-3">
        <h2 className="text-sm font-medium text-foreground/70">
          共 {segments.length} 個片段
        </h2>
        {segments.length === 0 && (
          <Card>
            <p className="text-sm text-foreground/50 text-center py-4">
              此工作階段尚無片段資料
            </p>
          </Card>
        )}
        {segments.map((seg) => (
          <SegmentEditor
            key={seg.id}
            segment={seg}
            onSave={handleSaveSegment}
          />
        ))}
      </section>

      {/* 匯出至 Fine-tune 資料集 */}
      <Card>
        <h2 className="text-base font-semibold text-foreground mb-4">
          匯出至 Fine-tune 資料集
        </h2>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="flex-1">
            <Input
              label="匯出至 Dataset ID"
              type="number"
              value={datasetId}
              onChange={(e) => setDatasetId(e.target.value)}
              placeholder="例：42"
              disabled={exporting}
            />
          </div>
          <Button
            onClick={handleExport}
            disabled={exporting || !datasetId.trim() || Number(datasetId) <= 0}
            className="shrink-0"
          >
            {exporting ? '匯出中…' : '確認匯出'}
          </Button>
        </div>

        {/* 匯出結果 */}
        {exportResult && (
          <p className="mt-3 text-sm text-green-600">
            已成功匯出 {exportResult.insertedCount} 筆至資料集 #{exportResult.datasetId}
          </p>
        )}
        {exportError && (
          <p className="mt-3 text-sm text-red-500" role="alert">
            {exportError}
          </p>
        )}
      </Card>
    </main>
  );
}
