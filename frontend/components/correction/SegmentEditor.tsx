'use client';

import { useState } from 'react';

import type { CorrectionSegment } from '@/lib/api/correction';
import { Button } from '@/components/ui/Button';

// ─── Props ────────────────────────────────────────────────────────────────────

interface SegmentEditorProps {
  segment: CorrectionSegment;
  /**
   * 儲存回呼：由父元件負責呼叫 CorrectionApi.updateSegment
   * @param segmentId  片段 ID
   * @param text       校正後文字
   * @param expectedVersion  目前版本號（用於 optimistic locking）
   */
  onSave: (segmentId: number, text: string, expectedVersion: number) => Promise<void>;
}

// ─── 工具：格式化秒數為 mm:ss.S ──────────────────────────────────────────────

function formatSec(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = (sec % 60).toFixed(1);
  return `${m.toString().padStart(2, '0')}:${s.padStart(4, '0')}`;
}

// ─── 元件 ────────────────────────────────────────────────────────────────────

export function SegmentEditor({ segment, onSave }: SegmentEditorProps) {
  // 編輯中文字，預設顯示已校正文字，若尚未校正則顯示原文
  const baseline = segment.corrected_text ?? segment.original_text;
  const [text, setText] = useState<string>(baseline);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // plan bug 修補：corrected_text 可能為 null，改用 baseline 比較
  const isUnchanged = text === baseline;
  const isDisabled = saving || isUnchanged;

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      await onSave(segment.segment_id, text, segment.version);
    } catch (err) {
      setError(err instanceof Error ? err.message : '儲存失敗，請重試');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col gap-2 p-4 rounded-xl bg-glass-50 backdrop-blur-sm border border-white/40">
      {/* 標頭：時間區間 + 語者 + 版本徽章 */}
      <div className="flex items-center gap-3 text-sm text-foreground/70">
        <span className="font-mono">
          {formatSec(segment.start_sec)} → {formatSec(segment.end_sec)}
        </span>
        {segment.speaker_label && (
          <span className="px-2 py-0.5 rounded-full bg-accent/10 text-accent text-xs font-medium">
            {segment.speaker_label}
          </span>
        )}
        <span className="ml-auto px-2 py-0.5 rounded-full bg-surface text-xs font-mono text-foreground/50">
          v{segment.version}
        </span>
      </div>

      {/* 原文（唯讀參考） */}
      {segment.corrected_text !== null && (
        <p className="text-xs text-foreground/50 line-through select-none">
          原文：{segment.original_text}
        </p>
      )}

      {/* 校正文字輸入框 */}
      <textarea
        className="w-full px-3 py-2 rounded-xl bg-glass-50 backdrop-blur-sm border border-white/40 focus:border-accent focus:outline-none resize-none text-sm text-foreground min-h-[80px]"
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={saving}
        aria-label="校正文字"
      />

      {/* 儲存列：按鈕 + 錯誤訊息 */}
      <div className="flex items-center gap-3">
        <Button
          onClick={handleSave}
          disabled={isDisabled}
          className="text-sm px-4 py-1.5"
        >
          {saving ? '儲存中…' : '儲存'}
        </Button>
        {error && (
          <span className="text-sm text-red-500" role="alert">
            {error}
          </span>
        )}
        {!error && !isUnchanged && !saving && (
          <span className="text-xs text-foreground/40">已修改，尚未儲存</span>
        )}
      </div>
    </div>
  );
}
