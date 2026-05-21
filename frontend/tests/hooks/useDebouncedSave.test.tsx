import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useDebouncedSave } from '@/hooks/useDebouncedSave';
import { useCorrectionStore } from '@/stores/correctionStore';

jest.useFakeTimers();

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  useCorrectionStore.setState(useCorrectionStore.getInitialState(), true);
});

describe('useDebouncedSave', () => {
  it('2 秒內多次 setDraft 只觸發 1 次 mutation（trailing）', async () => {
    const mutate = jest.fn(async () => ({}));
    renderHook(
      () => useDebouncedSave({ sessionId: 1, intervalMs: 2000, mutate }),
      { wrapper },
    );

    act(() => {
      useCorrectionStore.getState().setDraft(1, 'a', 1);
    });
    act(() => {
      jest.advanceTimersByTime(500);
      useCorrectionStore.getState().setDraft(1, 'ab', 1);
    });
    act(() => {
      jest.advanceTimersByTime(500);
      useCorrectionStore.getState().setDraft(1, 'abc', 1);
    });
    act(() => {
      jest.advanceTimersByTime(2100);
    });

    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate).toHaveBeenCalledWith({
      segmentId: 1, corrected_text: 'abc', expected_version: 1,
    });
  });

  it('mutation success 後 markSaveState=saved', async () => {
    const mutate = jest.fn(async () => ({ version: 2 }));
    renderHook(
      () => useDebouncedSave({ sessionId: 1, intervalMs: 100, mutate }),
      { wrapper },
    );

    act(() => {
      useCorrectionStore.getState().setDraft(5, 'x', 1);
    });
    // Advance timers to fire the 100ms debounce timeout.
    act(() => {
      jest.advanceTimersByTime(150);
    });
    // Flush the microtask chain produced by the async setTimeout callback.
    // Each `await` in the callback (markSaveState + mutate + markSaveState) needs
    // one microtask-flush turn. We flush 4 times to be safe.
    await act(async () => { await Promise.resolve(); });
    await act(async () => { await Promise.resolve(); });
    await act(async () => { await Promise.resolve(); });
    await act(async () => { await Promise.resolve(); });

    expect(useCorrectionStore.getState().saveStates.get(5)).toBe('saved');
  });
});
