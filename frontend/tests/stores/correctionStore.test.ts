import { useCorrectionStore } from '@/stores/correctionStore';

beforeEach(() => {
  useCorrectionStore.setState((useCorrectionStore as any).getInitialState(), true);
});

describe('correctionStore', () => {
  it('setFocused 更新 focusedSegmentId，其他欄位不變', () => {
    useCorrectionStore.getState().setFocused(42);
    expect(useCorrectionStore.getState().focusedSegmentId).toBe(42);
    expect(useCorrectionStore.getState().playbackTime).toBe(0);
  });

  it('setDraft 推 unsaved + 寫入 draftMap', () => {
    useCorrectionStore.getState().setDraft(1, 'hello', 3);
    const s = useCorrectionStore.getState();
    expect(s.saveStates.get(1)).toBe('unsaved');
    expect(s.draftMap.get(1)).toEqual({ text: 'hello', expectedVersion: 3 });
  });

  it('markSaveState 狀態轉移：unsaved → saving → saved', () => {
    const { setDraft, markSaveState } = useCorrectionStore.getState();
    setDraft(1, 'h', 1);
    markSaveState(1, 'saving');
    expect(useCorrectionStore.getState().saveStates.get(1)).toBe('saving');
    markSaveState(1, 'saved');
    expect(useCorrectionStore.getState().saveStates.get(1)).toBe('saved');
  });

  it('setLoopRange 設定/清除', () => {
    const { setLoopRange } = useCorrectionStore.getState();
    setLoopRange({ start: 1.0, end: 2.0 });
    expect(useCorrectionStore.getState().loopRange).toEqual({ start: 1.0, end: 2.0 });
    expect(useCorrectionStore.getState().loopMode).toBe('range');
    setLoopRange(null);
    expect(useCorrectionStore.getState().loopRange).toBeNull();
    expect(useCorrectionStore.getState().loopMode).toBe('segment');
  });
});
