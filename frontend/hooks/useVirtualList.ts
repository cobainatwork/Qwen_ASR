'use client';

import { useVirtualizer } from '@tanstack/react-virtual';
import { type RefObject } from 'react';

interface Options<T> {
  items: T[];
  scrollRef: RefObject<HTMLElement | null>;
  estimateSize: (index: number) => number;
  /** Items count threshold below which virtualisation is disabled. Default: 100. */
  threshold?: number;
  overscan?: number;
}

export function useVirtualList<T>({
  items,
  scrollRef,
  estimateSize,
  threshold = 100,
  overscan = 5,
}: Options<T>) {
  const isVirtual = items.length > threshold;
  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => scrollRef.current,
    estimateSize,
    overscan,
    enabled: isVirtual,
  });
  return { isVirtual, virtualizer };
}
