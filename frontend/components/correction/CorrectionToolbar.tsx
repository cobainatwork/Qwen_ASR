'use client';

import { useState } from 'react';

import {
  useEvaluateQualityMutation,
  useExportExcelMutation,
  useExportJsonlMutation,
} from '@/lib/api/correction';
import { useCorrectionStore } from '@/stores/correctionStore';

export interface CorrectionToolbarProps {
  sessionId: number;
}

/** createObjectURL + anchor click + deferred revoke（1 s）。 */
function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1_000);
}

export function CorrectionToolbar({ sessionId }: CorrectionToolbarProps) {
  const jsonlM = useExportJsonlMutation(sessionId);
  const excelM = useExportExcelMutation(sessionId);
  const qualityM = useEvaluateQualityMutation(sessionId);

  const [qualityResult, setQualityResult] = useState<string | null>(null);

  // 掃描 saveStates Map，任意一筆為 'unsaved' 或 'saving' 即視為有未儲存項目
  const hasUnsaved = useCorrectionStore((s) => {
    for (const state of s.saveStates.values()) {
      if (state === 'unsaved' || state === 'saving') return true;
    }
    return false;
  });

  /**
   * 匯出前若有未儲存編輯，以 window.confirm 詢問使用者是否繼續。
   * 使用者取消則不執行 action。
   */
  function confirmIfUnsaved(action: () => void): void {
    if (
      hasUnsaved &&
      !window.confirm(
        '您有未儲存的編輯，繼續匯出可能遺失這些變更。確定繼續？',
      )
    ) {
      return;
    }
    action();
  }

  return (
    <div
      role="toolbar"
      aria-label="工具列"
      className="flex items-center gap-2 px-4 py-2 border-t bg-white/70 text-sm"
    >
      {/* 全部儲存：V1 stub，後續任務補實作（plan note: 待 M2.x 集中儲存機制） */}
      <button
        type="button"
        aria-label="全部儲存"
        onClick={() =>
          alert(
            '全部儲存功能待後續任務實作（Phase A3 M2.x 集中儲存機制）。',
          )
        }
        className="px-3 py-1 rounded border border-gray-300 hover:bg-gray-50 disabled:opacity-50"
      >
        全部儲存
      </button>

      <button
        type="button"
        aria-label="匯出 JSONL"
        disabled={jsonlM.isPending}
        onClick={() =>
          confirmIfUnsaved(() => {
            jsonlM.mutate(undefined, {
              onSuccess: (blob) =>
                downloadBlob(blob, `correction_session_${sessionId}.jsonl`),
            });
          })
        }
        className="px-3 py-1 rounded border border-gray-300 hover:bg-gray-50 disabled:opacity-50"
      >
        {jsonlM.isPending ? '匯出中…' : '匯出 JSONL'}
      </button>

      <button
        type="button"
        aria-label="匯出 Excel"
        disabled={excelM.isPending}
        onClick={() =>
          confirmIfUnsaved(() => {
            excelM.mutate(undefined, {
              onSuccess: (blob) =>
                downloadBlob(blob, `correction_session_${sessionId}.xlsx`),
            });
          })
        }
        className="px-3 py-1 rounded border border-gray-300 hover:bg-gray-50 disabled:opacity-50"
      >
        {excelM.isPending ? '匯出中…' : '匯出 Excel'}
      </button>

      <button
        type="button"
        aria-label="品質評估"
        disabled={qualityM.isPending}
        onClick={() => {
          qualityM.mutate(undefined, {
            onSuccess: (result) =>
              setQualityResult(
                `品質分數：${result.score.toFixed(2)}，問題 ${result.issues.length} 筆`,
              ),
          });
        }}
        className="px-3 py-1 rounded border border-gray-300 hover:bg-gray-50 disabled:opacity-50"
      >
        {qualityM.isPending ? '評估中…' : '品質評估'}
      </button>

      {qualityResult && (
        <span className="ml-auto text-xs text-gray-600" aria-live="polite">
          {qualityResult}
        </span>
      )}
    </div>
  );
}
