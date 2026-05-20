import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock AudioUploader to two buttons exposing its callbacks; we test HomePage
// rehydrate behaviour, not AudioUploader's internals.
jest.mock('@/components/asr/AudioUploader', () => ({
  AudioUploader: ({
    onResult,
    onTranscribeStart,
  }: {
    onResult: (data: unknown, ms: number) => void;
    onTranscribeStart?: () => void;
  }) => {
    const FAKE = {
      transcription_id: 99,
      audio_file_id: 100,
      text: '新辨識內容',
      timestamps: null,
      speakers: null,
      diarization: null,
      language: null,
      duration_sec: 3,
      processing_duration_sec: 1,
      model_version: 'NEW',
      resampling_warning: false,
      vad_segments_count: 1,
      warnings: [],
    };
    return (
      <div>
        <button onClick={() => onTranscribeStart?.()}>mock-start</button>
        <button onClick={() => onResult(FAKE, 1234)}>mock-result</button>
      </div>
    );
  },
}));

import HomePage from '@/app/page';

const STORAGE_KEY = 'qwen-asr:last-transcribe-result';

const REHYDRATABLE_PAYLOAD = {
  data: {
    transcription_id: 1,
    audio_file_id: 2,
    text: '舊紀錄文字',
    timestamps: null,
    speakers: null,
    diarization: null,
    language: null,
    duration_sec: 5,
    processing_duration_sec: 1,
    model_version: 'OLD',
    resampling_warning: false,
    vad_segments_count: 1,
    warnings: [],
  },
  clientElapsedMs: 1500,
};

describe('HomePage rehydrate banner', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  test('shows rehydrate banner + restored result when sessionStorage has prior data', () => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(REHYDRATABLE_PAYLOAD));
    render(<HomePage />);

    expect(screen.getByText(/此為先前紀錄/)).toBeInTheDocument();
    expect(screen.getByText('舊紀錄文字')).toBeInTheDocument();
  });

  test('no banner when sessionStorage is empty', () => {
    render(<HomePage />);

    expect(screen.queryByText(/此為先前紀錄/)).not.toBeInTheDocument();
  });

  test('清除 button removes banner + result + sessionStorage entry', async () => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(REHYDRATABLE_PAYLOAD));
    render(<HomePage />);

    await userEvent.click(screen.getByRole('button', { name: /清除/ }));

    expect(screen.queryByText(/此為先前紀錄/)).not.toBeInTheDocument();
    expect(screen.queryByText('舊紀錄文字')).not.toBeInTheDocument();
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  test('fresh transcribe result does not show banner', async () => {
    render(<HomePage />);

    await userEvent.click(screen.getByRole('button', { name: 'mock-result' }));

    expect(screen.getByText('新辨識內容')).toBeInTheDocument();
    expect(screen.queryByText(/此為先前紀錄/)).not.toBeInTheDocument();
  });
});
