import { renderHook } from '@testing-library/react';
import { fireEvent } from '@testing-library/react';
import { useCorrectionShortcuts } from '@/hooks/useCorrectionShortcuts';
import { useCorrectionStore } from '@/stores/correctionStore';

const segments = [
  {
    id: 1, start_sec: 0, end_sec: 1, original_text: '', corrected_text: null,
    segment_index: 0, session_id: 1, version: 1, speaker_label: null,
    is_skipped: false, updated_at: '',
  } as any,
  {
    id: 2, start_sec: 1, end_sec: 2, original_text: '', corrected_text: null,
    segment_index: 1, session_id: 1, version: 1, speaker_label: null,
    is_skipped: false, updated_at: '',
  } as any,
];

describe('useCorrectionShortcuts', () => {
  it('Ctrl+S 觸發 onSave 並 preventDefault', () => {
    const onSave = jest.fn();
    renderHook(() => useCorrectionShortcuts({
      segments,
      onPlayToggle: jest.fn(),
      onSave,
      onNextAndSave: jest.fn(),
      onFocusSearch: jest.fn(),
    }));
    const ev = new KeyboardEvent('keydown', { code: 'KeyS', ctrlKey: true, bubbles: true });
    const prevSpy = jest.spyOn(ev, 'preventDefault');
    window.dispatchEvent(ev);
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(prevSpy).toHaveBeenCalled();
  });

  it('Space 在 textarea 中不觸發 onPlayToggle', () => {
    const onPlayToggle = jest.fn();
    renderHook(() => useCorrectionShortcuts({
      segments,
      onPlayToggle,
      onSave: jest.fn(),
      onNextAndSave: jest.fn(),
      onFocusSearch: jest.fn(),
    }));
    const textarea = document.createElement('textarea');
    document.body.appendChild(textarea);
    textarea.focus();
    fireEvent.keyDown(textarea, { code: 'Space' });
    expect(onPlayToggle).not.toHaveBeenCalled();
    textarea.remove();
  });

  it('Ctrl+Enter 觸發 onNextAndSave 並 preventDefault', () => {
    const onNextAndSave = jest.fn();
    renderHook(() => useCorrectionShortcuts({
      segments,
      onPlayToggle: jest.fn(),
      onSave: jest.fn(),
      onNextAndSave,
      onFocusSearch: jest.fn(),
    }));
    const ev = new KeyboardEvent('keydown', { code: 'Enter', ctrlKey: true, bubbles: true });
    const prevSpy = jest.spyOn(ev, 'preventDefault');
    window.dispatchEvent(ev);
    expect(onNextAndSave).toHaveBeenCalledTimes(1);
    expect(prevSpy).toHaveBeenCalled();
  });

  it('Space（非 textarea）觸發 onPlayToggle', () => {
    const onPlayToggle = jest.fn();
    renderHook(() => useCorrectionShortcuts({
      segments,
      onPlayToggle,
      onSave: jest.fn(),
      onNextAndSave: jest.fn(),
      onFocusSearch: jest.fn(),
    }));
    // ensure focus is on body (not a textarea)
    document.body.focus();
    const ev = new KeyboardEvent('keydown', { code: 'Space', bubbles: true });
    window.dispatchEvent(ev);
    expect(onPlayToggle).toHaveBeenCalledTimes(1);
  });

  it('ArrowRight 切到下一段', () => {
    const segs = [
      { id: 1 }, { id: 2 }, { id: 3 },
    ] as any[];
    useCorrectionStore.getState().setFocused(1);
    renderHook(() => useCorrectionShortcuts({
      segments: segs, onPlayToggle: jest.fn(), onSave: jest.fn(),
      onNextAndSave: jest.fn(), onFocusSearch: jest.fn(),
    }));
    window.dispatchEvent(new KeyboardEvent('keydown', { code: 'ArrowRight' }));
    expect(useCorrectionStore.getState().focusedSegmentId).toBe(2);
  });

  it('Home 跳第一段', () => {
    const segs = [{ id: 10 }, { id: 20 }] as any[];
    useCorrectionStore.getState().setFocused(20);
    renderHook(() => useCorrectionShortcuts({
      segments: segs, onPlayToggle: jest.fn(), onSave: jest.fn(),
      onNextAndSave: jest.fn(), onFocusSearch: jest.fn(),
    }));
    window.dispatchEvent(new KeyboardEvent('keydown', { code: 'Home' }));
    expect(useCorrectionStore.getState().focusedSegmentId).toBe(10);
  });
});
