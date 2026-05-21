import { renderHook, act } from '@testing-library/react';

import { useThrottledValue } from '@/hooks/useThrottledValue';

describe('useThrottledValue', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('leading edge：首次值立刻 emit', () => {
    const { result } = renderHook(({ v }) => useThrottledValue(v, 100), {
      initialProps: { v: 0 },
    });
    expect(result.current).toBe(0);
  });

  it('throttle window 內的多次更新只 emit 一次（trailing edge 拿最新值）', () => {
    const { result, rerender } = renderHook(({ v }) => useThrottledValue(v, 100), {
      initialProps: { v: 0 },
    });
    expect(result.current).toBe(0);

    // 0ms：leading 已 emit 0
    rerender({ v: 1 });
    act(() => {
      jest.advanceTimersByTime(20);
    });
    expect(result.current).toBe(0); // 仍在 throttle window 內，未 emit 1

    rerender({ v: 2 });
    act(() => {
      jest.advanceTimersByTime(20);
    });
    expect(result.current).toBe(0); // 仍未 emit

    rerender({ v: 3 });
    // 推進到 100ms，trailing 應 emit 最新 v=3
    act(() => {
      jest.advanceTimersByTime(60);
    });
    expect(result.current).toBe(3);
  });

  it('超過 throttle window 後下次更新立刻 emit', () => {
    const { result, rerender } = renderHook(({ v }) => useThrottledValue(v, 100), {
      initialProps: { v: 0 },
    });
    expect(result.current).toBe(0);

    // initial render 排了 trailing timer，advance 100ms 讓它 emit (lastEmitTs=100)
    // 再 advance 100ms 讓 elapsed=100ms 達 throttle window 邊界
    act(() => {
      jest.advanceTimersByTime(250);
    });

    rerender({ v: 5 });
    // 已超過 throttle window，新值應立刻 emit（leading）
    act(() => {
      jest.advanceTimersByTime(0);
    });
    expect(result.current).toBe(5);
  });

  it('unmount 取消 pending trailing timer，不再呼叫 setState', () => {
    const { result, rerender, unmount } = renderHook(({ v }) => useThrottledValue(v, 100), {
      initialProps: { v: 0 },
    });
    rerender({ v: 1 });
    unmount();
    // 推進時間，若沒清 timer 會炸 React warning（test 環境視為 fail）
    act(() => {
      jest.advanceTimersByTime(200);
    });
    // 沒 assert 因為 hook unmounted；測試重點是不 throw
    expect(result.current).toBe(0);
  });
});
