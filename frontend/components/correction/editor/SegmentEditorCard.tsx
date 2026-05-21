'use client';

import { useEffect, useState } from 'react';
import { useCorrectionStore } from '@/stores/correctionStore';
import { formatTimestamp } from '@/lib/format/time';
import { DiffText } from './DiffText';
import type { CorrectionSegment } from '@/lib/api/correction';

interface SegmentEditorCardProps {
  segment: CorrectionSegment;
}

/**
 * 單一校正片段的編輯卡片。
 *
 * 聚焦模式（focusMode）行為：
 * - isFocused（此卡片為 focused）→ 完整展開
 * - isShrunk（focusMode && !isFocused）→ 縮略成時間軸縮圖列
 */
export function SegmentEditorCard({ segment }: SegmentEditorCardProps) {
  const focusedId = useCorrectionStore((s) => s.focusedSegmentId);
  const focusMode = useCorrectionStore((s) => s.focusMode);
  const setDraft = useCorrectionStore((s) => s.setDraft);
  const saveState = useCorrectionStore((s) => s.saveStates.get(segment.id));
  const draftEntry = useCorrectionStore((s) => s.draftMap.get(segment.id));

  const isFocused = focusedId === segment.id;
  const isShrunk = focusMode && !isFocused;

  // 本地 textarea 狀態；初始化為 corrected_text，fallback 為 original_text
  const [local, setLocal] = useState(segment.corrected_text ?? segment.original_text);

  // 當 store draftMap 因外部更新而變動時（e.g. broadcast channel 同步），
  // hydrate 到本地 state，避免覆蓋使用者正在編輯的值。
  useEffect(() => {
    if (draftEntry?.text !== undefined && draftEntry.text !== local) {
      setLocal(draftEntry.text);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftEntry?.text]);

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setLocal(value);
    setDraft(segment.id, value, segment.version);
  };

  if (isShrunk) {
    return (
      <article
        role="article"
        className="shrunk cursor-pointer rounded border p-1 text-xs opacity-60 hover:opacity-80"
        style={{ minHeight: 24 }}
        onClick={() => useCorrectionStore.getState().setFocused(segment.id)}
      >
        #{segment.segment_index} {formatTimestamp(segment.start_sec)}
      </article>
    );
  }

  return (
    <article
      role="article"
      className={`mb-3 rounded border p-3${isFocused ? ' focused border-blue-500 shadow-sm' : ''}`}
    >
      <header className="mb-2 flex items-center justify-between text-xs text-gray-500">
        <span className="font-medium">
          {segment.speaker_label ?? '—'}
          {'　'}
          {formatTimestamp(segment.start_sec)} – {formatTimestamp(segment.end_sec)}
        </span>
        <span>
          {saveState === 'saving' && '儲存中…'}
          {saveState === 'saved' && '已儲存 ✓'}
          {saveState === 'unsaved' && '未儲存'}
          {saveState === 'conflict' && (
            <span className="text-red-500">衝突</span>
          )}
        </span>
      </header>

      {/* 原文（唯讀） */}
      <div
        data-testid="original-text"
        className="mb-2 rounded bg-gray-50 p-2 font-mono text-[13px] text-gray-600"
      >
        {segment.original_text}
      </div>

      {/* Diff 高亮預覽 */}
      <div className="mb-1 min-h-[1.5em]">
        <DiffText original={segment.original_text} corrected={local} />
      </div>

      {/* 可編輯 textarea */}
      <textarea
        value={local}
        onChange={handleChange}
        rows={3}
        className="mt-1 w-full rounded border p-2 text-[15px] leading-relaxed focus:outline-none focus:ring-1 focus:ring-blue-400"
      />
    </article>
  );
}

interface SegmentEditorCardListProps {
  segments: CorrectionSegment[];
}

export function SegmentEditorCardList({ segments }: SegmentEditorCardListProps) {
  return (
    <>
      {segments.map((s) => (
        <SegmentEditorCard key={s.id} segment={s} />
      ))}
    </>
  );
}
