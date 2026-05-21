'use client';

import { useCorrectionStore } from '@/stores/correctionStore';

export function SegmentListSearch({ speakers }: { speakers: string[] }) {
  const q = useCorrectionStore((s) => s.searchQuery);
  const setQ = useCorrectionStore((s) => s.setSearchQuery);
  const fs = useCorrectionStore((s) => s.filterSpeaker);
  const setFs = useCorrectionStore((s) => s.setFilterSpeaker);
  const ft = useCorrectionStore((s) => s.filterStatus);
  const setFt = useCorrectionStore((s) => s.setFilterStatus);

  return (
    <div className="p-2 space-y-1 border-b text-xs">
      <input
        type="search"
        aria-label="搜尋"
        placeholder="搜尋文字"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        className="w-full border rounded px-2 py-1"
      />
      <select
        aria-label="依語者"
        value={fs ?? ''}
        onChange={(e) => setFs(e.target.value || null)}
        className="w-full border rounded px-2 py-1"
      >
        <option value="">全部語者</option>
        {speakers.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>
      <select
        aria-label="依狀態"
        value={ft}
        onChange={(e) => setFt(e.target.value as Parameters<typeof setFt>[0])}
        className="w-full border rounded px-2 py-1"
      >
        <option value="all">全部</option>
        <option value="corrected">已校正</option>
        <option value="uncorrected">未校正</option>
        <option value="skipped">已跳過</option>
      </select>
    </div>
  );
}
