import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { TranscriptViewer } from '@/components/asr/TranscriptViewer';
import type { TranscribeData } from '@/lib/api/types';

const baseData: TranscribeData = {
  transcription_id: 1,
  audio_file_id: 2,
  text: '你好 世界',
  timestamps: [
    { start: 0.0, end: 0.8, text: '你好' },
    { start: 1.0, end: 2.0, text: '世界' },
  ],
  speakers: [
    { speaker: 'SPEAKER_00', start: 0, end: 1 },
    { speaker: 'SPEAKER_01', start: 1, end: 2 },
  ],
  diarization: null,
  language: 'zh',
  duration_sec: 2.0,
  processing_duration_sec: 0.5,
  model_version: 'TEST',
  resampling_warning: false,
  vad_segments_count: 2,
  warnings: [],
};

describe('TranscriptViewer', () => {
  beforeEach(() => {
    Element.prototype.scrollIntoView = jest.fn();
  });

  it('每 speaker turn 一個段落', () => {
    render(<TranscriptViewer data={baseData} currentTime={0} onSeek={() => {}} />);
    expect(screen.getByText('SPEAKER_00')).toBeInTheDocument();
    expect(screen.getByText('SPEAKER_01')).toBeInTheDocument();
    expect(screen.getByText('你好')).toBeInTheDocument();
    expect(screen.getByText('世界')).toBeInTheDocument();
  });

  it('點段落觸發 onSeek(segment.start)', async () => {
    const onSeek = jest.fn();
    render(<TranscriptViewer data={baseData} currentTime={0} onSeek={onSeek} />);
    await userEvent.click(screen.getByText('世界'));
    expect(onSeek).toHaveBeenCalledWith(1);
  });

  it('currentTime 落入第二段時，第二段標 aria-current', () => {
    const { container } = render(
      <TranscriptViewer data={baseData} currentTime={1.5} onSeek={() => {}} />,
    );
    const active = container.querySelector('[aria-current="true"]');
    expect(active).not.toBeNull();
    expect(active!.textContent).toContain('SPEAKER_01');
  });

  it('沒有 timestamps + 沒 speakers 時顯示純文字 fallback', () => {
    const empty: TranscribeData = { ...baseData, timestamps: null, speakers: null };
    render(<TranscriptViewer data={empty} currentTime={0} onSeek={() => {}} />);
    expect(screen.getByText('你好 世界')).toBeInTheDocument();
  });
});
