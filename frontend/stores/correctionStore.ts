import { create } from 'zustand';

export type SaveState = 'saved' | 'saving' | 'unsaved' | 'conflict';
export type LoopMode = 'segment' | 'range' | 'off';

export interface CorrectionState {
  sessionId: number | null;
  focusedSegmentId: number | null;
  playbackTime: number;
  playbackRate: number;
  loopMode: LoopMode;
  loopRange: { start: number; end: number } | null;
  focusMode: boolean;

  saveStates: Map<number, SaveState>;
  draftMap: Map<number, { text: string; expectedVersion: number }>;

  searchQuery: string;
  filterSpeaker: string | null;
  filterStatus: 'all' | 'corrected' | 'uncorrected' | 'skipped';
}

interface CorrectionActions {
  setSession(id: number | null): void;
  setFocused(id: number | null): void;
  setPlayback(t: number): void;
  setPlaybackRate(r: number): void;
  setLoopRange(r: { start: number; end: number } | null): void;
  setLoopMode(m: LoopMode): void;
  toggleFocusMode(): void;
  setDraft(id: number, text: string, expectedVersion: number): void;
  clearDraft(id: number): void;
  markSaveState(id: number, state: SaveState): void;
  setSearchQuery(q: string): void;
  setFilterSpeaker(s: string | null): void;
  setFilterStatus(s: CorrectionState['filterStatus']): void;
  reset(): void;
}

const INITIAL_STATE: CorrectionState = {
  sessionId: null,
  focusedSegmentId: null,
  playbackTime: 0,
  playbackRate: 1,
  loopMode: 'segment',
  loopRange: null,
  focusMode: false,
  saveStates: new Map(),
  draftMap: new Map(),
  searchQuery: '',
  filterSpeaker: null,
  filterStatus: 'all',
};

export const useCorrectionStore = create<CorrectionState & CorrectionActions>(
  (set, get) => ({
    ...INITIAL_STATE,

    setSession: (id) => set({ sessionId: id }),
    setFocused: (id) => set({ focusedSegmentId: id }),
    setPlayback: (t) => set({ playbackTime: t }),
    setPlaybackRate: (r) => set({ playbackRate: r }),
    setLoopRange: (r) =>
      set((s) => ({
        loopRange: r,
        loopMode: r ? 'range' : s.loopMode === 'range' ? 'segment' : s.loopMode,
      })),
    setLoopMode: (m) => set({ loopMode: m }),
    toggleFocusMode: () => set((s) => ({ focusMode: !s.focusMode })),

    setDraft: (id, text, expectedVersion) => {
      const draftMap = new Map(get().draftMap);
      draftMap.set(id, { text, expectedVersion });
      const saveStates = new Map(get().saveStates);
      saveStates.set(id, 'unsaved');
      set({ draftMap, saveStates });
    },
    clearDraft: (id) => {
      const draftMap = new Map(get().draftMap);
      draftMap.delete(id);
      set({ draftMap });
    },
    markSaveState: (id, state) => {
      const saveStates = new Map(get().saveStates);
      saveStates.set(id, state);
      set({ saveStates });
    },

    setSearchQuery: (q) => set({ searchQuery: q }),
    setFilterSpeaker: (s) => set({ filterSpeaker: s }),
    setFilterStatus: (s) => set({ filterStatus: s }),

    // Partial set (not `, true` full-replace) preserves action functions on
    // the store. Using full-replace with INITIAL_STATE wipes all actions —
    // and the next caller hits `setSession is not a function`. React.StrictMode
    // in dev double-mounts useEffect, so a buggy reset() on cleanup blows up
    // the second mount.
    reset: () => set({ ...INITIAL_STATE }),
  }),
);

// Expose getInitialState for test reset.
// Must include action functions so setState(..., true) (full-replace) keeps them intact.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
(useCorrectionStore as any).getInitialState = () => {
  const current = useCorrectionStore.getState();
  const actions = Object.fromEntries(
    Object.entries(current).filter(([, v]) => typeof v === 'function'),
  );
  return { ...INITIAL_STATE, ...actions };
};
