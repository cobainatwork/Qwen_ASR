import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { ExportButtons } from '@/components/asr/ExportButtons';
import type { TranscribeData } from '@/lib/api/types';

const data: TranscribeData = {
  transcription_id: 1,
  audio_file_id: 2,
  text: '你好',
  timestamps: [{ start: 0, end: 0.5, word: '你好' }],
  speakers: null,
  diarization: null,
  language: null,
  duration_sec: 0.5,
  processing_duration_sec: 0.1,
  model_version: 'T',
  resampling_warning: false,
  vad_segments_count: 1,
  warnings: [],
};

describe('ExportButtons', () => {
  beforeEach(() => {
    global.URL.createObjectURL = jest.fn(() => 'blob:mock');
    global.URL.revokeObjectURL = jest.fn();
  });

  it('renders three buttons for SRT, VTT, and JSON formats', () => {
    render(<ExportButtons data={data} baseFilename="test" />);
    expect(screen.getByRole('button', { name: /SRT/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /VTT/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /JSON/i })).toBeInTheDocument();
  });

  it('calls createObjectURL when SRT button is clicked', async () => {
    const user = userEvent.setup();
    render(<ExportButtons data={data} baseFilename="test" />);
    await user.click(screen.getByRole('button', { name: /SRT/i }));
    expect(global.URL.createObjectURL).toHaveBeenCalled();
  });

  it('calls createObjectURL when VTT button is clicked', async () => {
    const user = userEvent.setup();
    render(<ExportButtons data={data} baseFilename="test" />);
    await user.click(screen.getByRole('button', { name: /VTT/i }));
    expect(global.URL.createObjectURL).toHaveBeenCalled();
  });

  it('calls createObjectURL when JSON button is clicked', async () => {
    const user = userEvent.setup();
    render(<ExportButtons data={data} baseFilename="test" />);
    await user.click(screen.getByRole('button', { name: /JSON/i }));
    expect(global.URL.createObjectURL).toHaveBeenCalled();
  });
});
