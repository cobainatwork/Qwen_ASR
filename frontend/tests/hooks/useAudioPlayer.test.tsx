import { renderHook, act } from '@testing-library/react';

import { useAudioPlayer } from '@/hooks/useAudioPlayer';

describe('useAudioPlayer', () => {
  it('沒 audioUrl 時 isReady=false', () => {
    const { result } = renderHook(() =>
      useAudioPlayer({ audioUrl: null, containerRef: { current: null } }),
    );
    expect(result.current.isReady).toBe(false);
    expect(result.current.isPlaying).toBe(false);
  });

  it('暴露 play/pause/seek/setRate/setVolume API', () => {
    const { result } = renderHook(() =>
      useAudioPlayer({ audioUrl: null, containerRef: { current: null } }),
    );
    expect(typeof result.current.play).toBe('function');
    expect(typeof result.current.pause).toBe('function');
    expect(typeof result.current.seek).toBe('function');
    expect(typeof result.current.setRate).toBe('function');
    expect(typeof result.current.setVolume).toBe('function');
  });

  it('沒 instance 時呼叫 play/pause 不爆', () => {
    const { result } = renderHook(() =>
      useAudioPlayer({ audioUrl: null, containerRef: { current: null } }),
    );
    expect(() => act(() => result.current.play())).not.toThrow();
    expect(() => act(() => result.current.pause())).not.toThrow();
    expect(() => act(() => result.current.seek(0))).not.toThrow();
  });
});
