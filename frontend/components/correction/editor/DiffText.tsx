'use client';

import { useMemo } from 'react';
import { computeDiff } from '@/lib/correction/diff';

interface DiffTextProps {
  original: string;
  corrected: string;
}

/**
 * 顯示 original → corrected 的 inline diff。
 * - 刪除：紅底 + 刪除線（bg-red-100 line-through）
 * - 插入：綠底（bg-green-100）
 * - 相同：無樣式
 */
export function DiffText({ original, corrected }: DiffTextProps) {
  const ops = useMemo(() => computeDiff(original, corrected), [original, corrected]);

  return (
    <span className="font-sans text-[15px] leading-relaxed">
      {ops.map((op, i) => {
        if (op.type === 'equal') {
          return <span key={i}>{op.text}</span>;
        }
        if (op.type === 'delete') {
          return (
            <span key={i} className="bg-red-100 line-through text-red-700">
              {op.text}
            </span>
          );
        }
        // insert
        return (
          <span key={i} className="bg-green-100 text-green-800">
            {op.text}
          </span>
        );
      })}
    </span>
  );
}
