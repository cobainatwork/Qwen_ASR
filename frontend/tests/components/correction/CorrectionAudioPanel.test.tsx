import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CorrectionAudioPanel } from '@/components/correction/audio/CorrectionAudioPanel';
import { useCorrectionStore } from '@/stores/correctionStore';

// ── stable mock for useCorrectionAudio ───────────────────────────────────────
// We mock the hook so that the panel tests are not sensitive to wavesurfer
// internals, and so we can assert on seek/play calls from focusedSegmentId changes.

const mockPlay = jest.fn();
const mockPause = jest.fn();
const mockSeekToSegment = jest.fn();
const mockSetRate = jest.fn();

// isPlaying is controlled per-test via this variable.
let mockIsPlaying = false;

jest.mock('@/hooks/useCorrectionAudio', () => ({
  useCorrectionAudio: () => ({
    play: mockPlay,
    pause: mockPause,
    seek: jest.fn(),
    setRate: mockSetRate,
    seekToSegment: mockSeekToSegment,
    get isPlaying() { return mockIsPlaying; },
  }),
}));

// ── fixtures ─────────────────────────────────────────────────────────────────

const session = {
  id: 1,
  transcription_id: 99,
  audio_file_id: 42,
  name: 'test',
  status: 'in_progress',
  created_at: '',
  updated_at: '',
} as any;

const segments = [
  {
    id: 1,
    segment_index: 0,
    start_sec: 0,
    end_sec: 1,
    original_text: 'a',
    corrected_text: null,
    speaker_label: 'S0',
    is_skipped: false,
    version: 1,
    session_id: 1,
    updated_at: '',
  } as any,
  {
    id: 2,
    segment_index: 1,
    start_sec: 1,
    end_sec: 2,
    original_text: 'b',
    corrected_text: null,
    speaker_label: 'S1',
    is_skipped: false,
    version: 1,
    session_id: 1,
    updated_at: '',
  } as any,
];

// ── setup / teardown ─────────────────────────────────────────────────────────

beforeEach(() => {
  useCorrectionStore.setState(useCorrectionStore.getInitialState(), true);
  mockPlay.mockClear();
  mockPause.mockClear();
  mockSeekToSegment.mockClear();
  mockSetRate.mockClear();
  mockIsPlaying = false;
});

// ── tests ─────────────────────────────────────────────────────────────────────

describe('CorrectionAudioPanel', () => {
  it('renders waveform container, play button, rate select, stats', () => {
    render(<CorrectionAudioPanel session={session} segments={segments} />);
    expect(screen.getByTestId('waveform-container')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /播放/ })).toBeInTheDocument();
    expect(screen.getByLabelText('播放速度')).toBeInTheDocument();
    expect(screen.getByText(/總段落/)).toBeInTheDocument();
  });

  it('speed select 切換更新 store playbackRate', async () => {
    render(<CorrectionAudioPanel session={session} segments={segments} />);
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText('播放速度'), '1.5');
    expect(useCorrectionStore.getState().playbackRate).toBe(1.5);
  });

  it('focusedSegmentId 變更 → seekToSegment + play 各呼叫一次', () => {
    render(<CorrectionAudioPanel session={session} segments={segments} />);

    act(() => {
      useCorrectionStore.getState().setFocused(1);
    });

    expect(mockSeekToSegment).toHaveBeenCalledTimes(1);
    expect(mockSeekToSegment).toHaveBeenCalledWith(segments[0]);
    expect(mockPlay).toHaveBeenCalledTimes(1);
  });

  it('focusedSegmentId 變更兩次 → seekToSegment + play 各呼叫兩次（每次 focus 一次，非每幀）', () => {
    render(<CorrectionAudioPanel session={session} segments={segments} />);

    act(() => {
      useCorrectionStore.getState().setFocused(1);
    });
    act(() => {
      useCorrectionStore.getState().setFocused(2);
    });

    expect(mockSeekToSegment).toHaveBeenCalledTimes(2);
    expect(mockPlay).toHaveBeenCalledTimes(2);
    expect(mockSeekToSegment).toHaveBeenNthCalledWith(2, segments[1]);
  });

  it('playToggle 呼叫 pause 當 isPlaying=true', () => {
    mockIsPlaying = true;
    const ref = { current: null } as any;
    const { rerender } = render(
      <CorrectionAudioPanel ref={ref} session={session} segments={segments} />,
    );
    // Re-render so useImperativeHandle sees the updated mockIsPlaying.
    rerender(<CorrectionAudioPanel ref={ref} session={session} segments={segments} />);

    act(() => { ref.current?.playToggle(); });

    expect(mockPause).toHaveBeenCalledTimes(1);
    expect(mockPlay).toHaveBeenCalledTimes(0);
  });

  it('playToggle 呼叫 play 當 isPlaying=false', () => {
    mockIsPlaying = false;
    const ref = { current: null } as any;
    render(<CorrectionAudioPanel ref={ref} session={session} segments={segments} />);

    act(() => { ref.current?.playToggle(); });

    expect(mockPlay).toHaveBeenCalledTimes(1);
    expect(mockPause).toHaveBeenCalledTimes(0);
  });
});
