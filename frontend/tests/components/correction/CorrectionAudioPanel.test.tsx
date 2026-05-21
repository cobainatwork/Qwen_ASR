import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CorrectionAudioPanel } from '@/components/correction/audio/CorrectionAudioPanel';
import { useCorrectionStore } from '@/stores/correctionStore';

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

beforeEach(() => {
  useCorrectionStore.setState(useCorrectionStore.getInitialState(), true);
});

describe('CorrectionAudioPanel', () => {
  it('renders waveform container, play button, rate select, stats', () => {
    render(<CorrectionAudioPanel session={session} segments={segments} />);
    expect(screen.getByTestId('waveform-container')).toBeInTheDocument();
    // getByRole narrows to button role, avoiding collision with the rate <select>
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
});
