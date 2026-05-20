import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { AudioUploader } from '@/components/asr/AudioUploader';
import { AuthProvider } from '@/components/auth/AuthProvider';

describe('AudioUploader', () => {
  beforeEach(() => {
    localStorage.clear();
    global.fetch = jest.fn(() =>
      Promise.resolve({
        json: () =>
          Promise.resolve({
            success: true,
            data: {
              transcription_id: 1,
              audio_file_id: 2,
              text: '測試文字',
              duration_sec: 1.0,
              processing_duration_sec: 0.5,
              model_version: 'MOCK',
              resampling_warning: false,
              vad_segments_count: 1,
              warnings: [],
            },
            error: null,
          }),
      }),
    ) as jest.Mock;
  });

  it('shows error if no token', async () => {
    const onResult = jest.fn();
    render(<AuthProvider><AudioUploader onResult={onResult} /></AuthProvider>);

    const file = new File(['fake'], 'a.wav', { type: 'audio/wav' });
    const input = screen.getByLabelText('選擇音檔') as HTMLInputElement;
    await userEvent.upload(input, file);

    await userEvent.click(screen.getByRole('button', { name: '開始辨識' }));

    expect(await screen.findByText(/請先在.*金鑰.*頁設定/)).toBeInTheDocument();
    expect(onResult).not.toHaveBeenCalled();
  });

  it('calls onResult when token present', async () => {
    localStorage.setItem('qwen-asr-token', 'test-token');
    const onResult = jest.fn();
    render(<AuthProvider><AudioUploader onResult={onResult} /></AuthProvider>);

    const file = new File(['fake'], 'a.wav', { type: 'audio/wav' });
    await userEvent.upload(screen.getByLabelText('選擇音檔') as HTMLInputElement, file);
    await userEvent.click(screen.getByRole('button', { name: '開始辨識' }));

    await waitFor(() => expect(onResult).toHaveBeenCalled());
    expect(onResult).toHaveBeenCalledWith(expect.objectContaining({ text: '測試文字' }), expect.any(Number));
  });

  it('selecting Chinese sends language: "Chinese" in options_json', async () => {
    localStorage.setItem('qwen-asr-token', 'test-token');
    const onResult = jest.fn();
    render(<AuthProvider><AudioUploader onResult={onResult} /></AuthProvider>);

    const file = new File(['fake'], 'a.wav', { type: 'audio/wav' });
    await userEvent.upload(screen.getByLabelText('選擇音檔') as HTMLInputElement, file);
    await userEvent.selectOptions(screen.getByLabelText('選擇辨識語言'), 'Chinese');
    await userEvent.click(screen.getByRole('button', { name: '開始辨識' }));

    await waitFor(() => expect(onResult).toHaveBeenCalled());

    const fetchMock = global.fetch as jest.Mock;
    const callArgs = fetchMock.mock.calls[fetchMock.mock.calls.length - 1];
    const formData = callArgs[1].body as FormData;
    const optionsJson = formData.get('options_json') as string;
    expect(JSON.parse(optionsJson)).toEqual({ language: 'Chinese' });
  });

  it('選檔時觸發 onFileSelected', async () => {
    const onResult = jest.fn();
    const onFileSelected = jest.fn();
    render(
      <AuthProvider>
        <AudioUploader onResult={onResult} onFileSelected={onFileSelected} />
      </AuthProvider>,
    );
    const file = new File(['fake'], 'a.wav', { type: 'audio/wav' });
    const input = screen.getByLabelText('選擇音檔') as HTMLInputElement;
    await userEvent.upload(input, file);
    expect(onFileSelected).toHaveBeenCalledWith(file);
  });

  it('default auto omits language from options_json', async () => {
    localStorage.setItem('qwen-asr-token', 'test-token');
    const onResult = jest.fn();
    render(<AuthProvider><AudioUploader onResult={onResult} /></AuthProvider>);

    const file = new File(['fake'], 'a.wav', { type: 'audio/wav' });
    await userEvent.upload(screen.getByLabelText('選擇音檔') as HTMLInputElement, file);
    // 不選 language，保留預設「自動偵測」
    await userEvent.click(screen.getByRole('button', { name: '開始辨識' }));

    await waitFor(() => expect(onResult).toHaveBeenCalled());

    const fetchMock = global.fetch as jest.Mock;
    const callArgs = fetchMock.mock.calls[fetchMock.mock.calls.length - 1];
    const formData = callArgs[1].body as FormData;
    const parsed = JSON.parse(formData.get('options_json') as string);
    expect(parsed.language).toBeUndefined();
  });
});
