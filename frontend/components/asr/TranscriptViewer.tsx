'use client';

import { useEffect, useMemo, useRef } from 'react';

import type { TranscribeData } from '@/lib/api/types';
import { buildSegments } from '@/lib/asr/segments';
import { speakerColor, speakerBgColor } from '@/lib/asr/speakerColors';
import { formatTimestamp } from '@/lib/format/time';

interface Props {
  data: TranscribeData;
  currentTime: number;
  onSeek: (seconds: number) => void;
}

export function TranscriptViewer({ data, currentTime, onSeek }: Props) {
  const segments = useMemo(
    () => buildSegments(data.timestamps, data.speakers, data.text),
    [data.timestamps, data.speakers, data.text],
  );
  const activeIdx = segments.findIndex((s) => currentTime >= s.start && currentTime < s.end);
  const refs = useRef<(HTMLLIElement | null)[]>([]);

  useEffect(() => {
    if (activeIdx >= 0) {
      refs.current[activeIdx]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }, [activeIdx]);

  if (segments.length === 0 || (segments.length === 1 && segments[0].text === '')) {
    return (
      <p className="text-sm text-foreground/60 italic px-4 py-3">
        辨識結果為空字串（音檔可能無有效語音段，或全為靜音 / 噪音）
      </p>
    );
  }

  return (
    <ol className="space-y-2 px-4 py-3" role="list">
      {segments.map((seg, i) => (
        <li
          key={i}
          ref={(el) => {
            refs.current[i] = el;
          }}
          aria-current={i === activeIdx ? 'true' : undefined}
          className={`rounded-xl border transition-colors ${
            i === activeIdx
              ? 'border-blue-400/60 bg-blue-50/70'
              : 'border-foreground/10 bg-white/40'
          }`}
        >
          <button
            type="button"
            onClick={() => onSeek(seg.start)}
            className="block w-full text-left px-3 py-2 cursor-pointer hover:bg-white/30 rounded-xl"
          >
            <div className="flex items-center gap-2 mb-1">
              <span
                className="inline-block rounded px-1.5 py-0.5 text-xs font-medium text-white"
                style={{ backgroundColor: speakerColor(seg.speaker) }}
              >
                {seg.speaker}
              </span>
              <span className="font-mono text-xs text-foreground/60 tabular-nums">
                {formatTimestamp(seg.start)} - {formatTimestamp(seg.end)}
              </span>
            </div>
            <p
              className="text-sm leading-relaxed whitespace-pre-wrap"
              style={{
                backgroundColor:
                  i === activeIdx ? speakerBgColor(seg.speaker) : 'transparent',
              }}
            >
              {seg.text || <span className="text-foreground/40 italic">（無文字）</span>}
            </p>
          </button>
        </li>
      ))}
    </ol>
  );
}
