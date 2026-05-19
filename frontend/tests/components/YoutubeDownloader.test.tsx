import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { AuthProvider } from '@/components/auth/AuthProvider';
import { YoutubeDownloader } from '@/components/youtube/YoutubeDownloader';

describe('YoutubeDownloader', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('prompts to set token when none is configured', () => {
    render(
      <AuthProvider>
        <YoutubeDownloader onTranscribed={() => {}} />
      </AuthProvider>,
    );
    expect(screen.getByText(/請先在.*金鑰.*頁設定/)).toBeInTheDocument();
  });

  it('submits URL and refreshes downloads list', async () => {
    localStorage.setItem('qwen-asr-token', 'test-token');
    const mockFetch = jest.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (typeof url === 'string' && url.includes('/downloads')) {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              success: true,
              data: [
                {
                  id: 1,
                  url: 'https://youtu.be/abc',
                  video_title: 'Test Video',
                  audio_file_id: 100,
                  status: 'completed',
                  error_message: null,
                  file_size: 1048576,
                  duration_sec: 60,
                  created_at: '2026-05-19T00:00:00Z',
                  updated_at: '2026-05-19T00:01:00Z',
                },
              ],
              error: null,
            }),
        });
      }
      if (typeof url === 'string' && url.endsWith('/download') && init?.method === 'POST') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              success: true,
              data: {
                id: 1,
                url: 'https://youtu.be/abc',
                video_title: null,
                audio_file_id: null,
                status: 'pending',
                error_message: null,
                file_size: null,
                duration_sec: null,
                created_at: '2026-05-19T00:00:00Z',
                updated_at: '2026-05-19T00:00:00Z',
              },
              error: null,
            }),
        });
      }
      return Promise.reject(new Error(`unexpected fetch ${url}`));
    });
    global.fetch = mockFetch as unknown as typeof fetch;

    render(
      <AuthProvider>
        <YoutubeDownloader onTranscribed={() => {}} />
      </AuthProvider>,
    );

    await userEvent.type(
      screen.getByLabelText('YouTube URL'),
      'https://youtu.be/abc',
    );
    await userEvent.click(screen.getByRole('button', { name: '下載' }));

    await waitFor(() => {
      expect(screen.getByText('Test Video')).toBeInTheDocument();
    });
    expect(screen.getByText('已完成')).toBeInTheDocument();
  });

  it('completed download triggers transcribe-stored on 辨識 click', async () => {
    localStorage.setItem('qwen-asr-token', 'test-token');
    const transcribeStoredCalls: string[] = [];
    const mockFetch = jest.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (typeof url === 'string' && url.includes('/transcribe-stored/100')) {
        transcribeStoredCalls.push(url);
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              success: true,
              data: {
                transcription_id: 7,
                audio_file_id: 100,
                text: '辨識成功',
                duration_sec: 60,
                processing_duration_sec: 5,
                model_version: 'MOCK',
                resampling_warning: false,
                vad_segments_count: 1,
                warnings: [],
              },
              error: null,
            }),
        });
      }
      if (typeof url === 'string' && url.includes('/downloads')) {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              success: true,
              data: [
                {
                  id: 1,
                  url: 'https://youtu.be/abc',
                  video_title: 'Done Video',
                  audio_file_id: 100,
                  status: 'completed',
                  error_message: null,
                  file_size: 1048576,
                  duration_sec: 60,
                  created_at: '2026-05-19T00:00:00Z',
                  updated_at: '2026-05-19T00:01:00Z',
                },
              ],
              error: null,
            }),
        });
      }
      void init;
      return Promise.reject(new Error(`unexpected fetch ${url}`));
    });
    global.fetch = mockFetch as unknown as typeof fetch;

    const onTranscribed = jest.fn();
    render(
      <AuthProvider>
        <YoutubeDownloader onTranscribed={onTranscribed} />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText('Done Video')).toBeInTheDocument();
    });
    await userEvent.click(screen.getByRole('button', { name: '辨識' }));

    await waitFor(() => expect(onTranscribed).toHaveBeenCalled());
    expect(transcribeStoredCalls).toHaveLength(1);
    expect(transcribeStoredCalls[0]).toContain('/api/v1/asr/transcribe-stored/100');
    expect(onTranscribed).toHaveBeenCalledWith(
      expect.objectContaining({ text: '辨識成功' }),
    );
  });

  it('passes selected language to transcribe-stored', async () => {
    localStorage.setItem('qwen-asr-token', 'test-token');
    const transcribeBodies: string[] = [];
    const mockFetch = jest.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (typeof url === 'string' && url.endsWith('/transcribe-stored/100')) {
        const body = init?.body as FormData;
        transcribeBodies.push(body.get('options_json') as string);
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              success: true,
              data: {
                transcription_id: 1,
                audio_file_id: 100,
                text: 'X',
                duration_sec: 1,
                processing_duration_sec: 1,
                model_version: 'M',
                resampling_warning: false,
                vad_segments_count: 0,
                warnings: [],
              },
              error: null,
            }),
        });
      }
      if (typeof url === 'string' && url.includes('/downloads')) {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              success: true,
              data: [
                {
                  id: 1,
                  url: 'u',
                  video_title: 'T',
                  audio_file_id: 100,
                  status: 'completed',
                  error_message: null,
                  file_size: 1,
                  duration_sec: 1,
                  created_at: '2026-01-01T00:00:00Z',
                  updated_at: '2026-01-01T00:00:00Z',
                },
              ],
              error: null,
            }),
        });
      }
      return Promise.reject(new Error(`unexpected ${url}`));
    });
    global.fetch = mockFetch as unknown as typeof fetch;

    render(
      <AuthProvider>
        <YoutubeDownloader onTranscribed={() => {}} />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByText('T')).toBeInTheDocument());
    await userEvent.selectOptions(
      screen.getByLabelText('YouTube 辨識語言'),
      'Chinese',
    );
    await userEvent.click(screen.getByRole('button', { name: '辨識' }));

    await waitFor(() => expect(transcribeBodies).toHaveLength(1));
    expect(JSON.parse(transcribeBodies[0])).toEqual({ language: 'Chinese' });
  });
});
