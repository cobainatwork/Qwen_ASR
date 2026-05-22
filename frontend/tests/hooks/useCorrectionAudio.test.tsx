/**
 * Tests for useCorrectionAudio
 *
 * Key invariants verified:
 * 1. All returned function refs are stable across renders (useCallback).
 * 2. seekToSegment calls ws.setTime() but NOT ws.zoom().
 * 3. isPlaying tracks ws 'play' / 'pause' / 'finish' events.
 */
import { renderHook, act } from '@testing-library/react';
import WaveSurfer from 'wavesurfer.js';
import type { FakeWaveSurfer } from '../../__mocks__/wavesurfer.js';
import { useCorrectionAudio } from '@/hooks/useCorrectionAudio';
import type { CorrectionSegment } from '@/lib/api/correction';

// ── helpers ──────────────────────────────────────────────────────────────────

// AuthContext is required by the hook; supply a minimal provider.
import React from 'react';
import { AuthContext } from '@/components/auth/AuthProvider';

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <AuthContext.Provider value={{ token: 'test-token', setToken: () => {} } as any}>
      {children}
    </AuthContext.Provider>
  );
}

const seg: CorrectionSegment = {
  id: 1,
  segment_index: 0,
  start_sec: 5,
  end_sec: 10,
  original_text: 'hello',
  corrected_text: null,
  speaker_label: 'S0',
  is_skipped: false,
  version: 1,
  session_id: 1,
  updated_at: '',
} as any;

function makeContainerRef() {
  return { current: document.createElement('div') };
}

// Retrieve the last WaveSurfer instance created by the mock factory.
function getLastWs(): FakeWaveSurfer {
  const factory = (WaveSurfer as any).create as jest.Mock;
  return factory.mock.results[factory.mock.results.length - 1].value as FakeWaveSurfer;
}

// Simulate a wavesurfer event by calling the registered handler(s).
function emitWsEvent(ws: FakeWaveSurfer, event: string) {
  const calls = (ws.on as jest.Mock).mock.calls as [string, () => void][];
  calls.filter(([e]) => e === event).forEach(([, cb]) => cb());
}

beforeEach(() => {
  jest.clearAllMocks();
  // Reset fetch mock so the hook's async load doesn't throw.
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    blob: () => Promise.resolve(new Blob(['audio'])),
  }) as any;
  global.URL.createObjectURL = jest.fn(() => 'blob:mock');
  global.URL.revokeObjectURL = jest.fn();
});

// ── Test 1: stable refs ───────────────────────────────────────────────────────

describe('useCorrectionAudio — stable function refs', () => {
  it('play, pause, seek, setRate, seekToSegment are the same reference across re-renders', () => {
    const containerRef = makeContainerRef();
    const { result, rerender } = renderHook(
      () => useCorrectionAudio({ audioUrl: '/api/v1/audio/1/stream', containerRef, segments: [seg] }),
      { wrapper },
    );

    const first = {
      play: result.current.play,
      pause: result.current.pause,
      seek: result.current.seek,
      setRate: result.current.setRate,
      seekToSegment: result.current.seekToSegment,
    };

    // Force a re-render without changing any deps.
    rerender();

    expect(result.current.play).toBe(first.play);
    expect(result.current.pause).toBe(first.pause);
    expect(result.current.seek).toBe(first.seek);
    expect(result.current.setRate).toBe(first.setRate);
    expect(result.current.seekToSegment).toBe(first.seekToSegment);
  });
});

// ── Test 2: seekToSegment calls setTime but NOT zoom ─────────────────────────

describe('useCorrectionAudio — seekToSegment', () => {
  it('calls ws.setTime(seg.start_sec) and does NOT call ws.zoom()', async () => {
    const containerRef = makeContainerRef();
    const { result } = renderHook(
      () => useCorrectionAudio({ audioUrl: '/api/v1/audio/1/stream', containerRef, segments: [seg] }),
      { wrapper },
    );

    const ws = getLastWs();

    act(() => {
      result.current.seekToSegment(seg);
    });

    expect(ws.setTime).toHaveBeenCalledWith(5);
    expect(ws.zoom).not.toHaveBeenCalled();
  });
});

// ── Test 3: isPlaying tracks ws events ───────────────────────────────────────
// IMPORTANT: segments must be a stable reference (module-level const, not `[]`
// literal). A new `[]` on each renderHook callback re-render would cause the
// hook's useEffect to re-run (segments is a dep), triggering cleanup
// (cancelled=true) and a new ws instance — the old event handler would then
// be a no-op. This mirrors the useMemo fix applied in the page component.

const EMPTY_SEGMENTS: CorrectionSegment[] = [];

describe('useCorrectionAudio — isPlaying', () => {
  it('starts as false', () => {
    const containerRef = makeContainerRef();
    const { result } = renderHook(
      () => useCorrectionAudio({ audioUrl: '/api/v1/audio/1/stream', containerRef, segments: EMPTY_SEGMENTS }),
      { wrapper },
    );
    expect(result.current.isPlaying).toBe(false);
  });

  it('becomes true on ws "play" event', async () => {
    const containerRef = makeContainerRef();
    const { result } = renderHook(
      () => useCorrectionAudio({ audioUrl: '/api/v1/audio/1/stream', containerRef, segments: EMPTY_SEGMENTS }),
      { wrapper },
    );
    // Flush the async IIFE (fetch → blob → ws.load) so the effect settles.
    await act(async () => {});
    const ws = getLastWs();

    act(() => { emitWsEvent(ws, 'play'); });
    expect(result.current.isPlaying).toBe(true);
  });

  it('becomes false on ws "pause" event after play', async () => {
    const containerRef = makeContainerRef();
    const { result } = renderHook(
      () => useCorrectionAudio({ audioUrl: '/api/v1/audio/1/stream', containerRef, segments: EMPTY_SEGMENTS }),
      { wrapper },
    );
    await act(async () => {});
    const ws = getLastWs();

    act(() => { emitWsEvent(ws, 'play'); });
    expect(result.current.isPlaying).toBe(true);

    act(() => { emitWsEvent(ws, 'pause'); });
    expect(result.current.isPlaying).toBe(false);
  });

  it('becomes false on ws "finish" event after play', async () => {
    const containerRef = makeContainerRef();
    const { result } = renderHook(
      () => useCorrectionAudio({ audioUrl: '/api/v1/audio/1/stream', containerRef, segments: EMPTY_SEGMENTS }),
      { wrapper },
    );
    await act(async () => {});
    const ws = getLastWs();

    act(() => { emitWsEvent(ws, 'play'); });
    expect(result.current.isPlaying).toBe(true);

    act(() => { emitWsEvent(ws, 'finish'); });
    expect(result.current.isPlaying).toBe(false);
  });
});
