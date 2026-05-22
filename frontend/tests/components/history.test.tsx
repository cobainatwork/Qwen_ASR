import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockPush = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

jest.mock('@/lib/api/asr', () => ({
  useTranscriptionsListQuery: jest.fn(),
}));

jest.mock('@/lib/api/correction', () => ({
  useCreateCorrectionSessionMutation: jest.fn(),
}));

import HistoryPage from '@/app/history/page';
import { useTranscriptionsListQuery } from '@/lib/api/asr';
import { useCreateCorrectionSessionMutation } from '@/lib/api/correction';

const mockQuery = useTranscriptionsListQuery as jest.Mock;
const mockMutation = useCreateCorrectionSessionMutation as jest.Mock;

const MOCK_TX = {
  id: 7,
  file_name: 'test.wav',
  source: 'upload',
  status: 'completed',
  duration_sec: 30.5,
  language: 'zh',
  model_version: 'v1',
  created_at: '2026-05-22T10:00:00Z',
  updated_at: '2026-05-22T10:01:00Z',
};

describe('HistoryPage', () => {
  afterEach(() => {
    jest.clearAllMocks();
    mockPush.mockReset();
  });

  test('shows loading state', () => {
    mockQuery.mockReturnValue({ isLoading: true, isError: false, data: undefined });
    mockMutation.mockReturnValue({ mutateAsync: jest.fn(), isPending: false });
    render(<HistoryPage />);
    expect(screen.getByText(/載入中/)).toBeInTheDocument();
  });

  test('shows error state', () => {
    mockQuery.mockReturnValue({ isLoading: false, isError: true, data: undefined });
    mockMutation.mockReturnValue({ mutateAsync: jest.fn(), isPending: false });
    render(<HistoryPage />);
    expect(screen.getByText(/載入失敗/)).toBeInTheDocument();
  });

  test('shows empty state when no transcriptions', () => {
    mockQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [], pagination: { total: 0, page: 1, limit: 20, total_pages: 1 } },
    });
    mockMutation.mockReturnValue({ mutateAsync: jest.fn(), isPending: false });
    render(<HistoryPage />);
    expect(screen.getByText(/目前沒有歷史辨識紀錄/)).toBeInTheDocument();
  });

  test('renders transcription rows with file name, status, duration', () => {
    mockQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        items: [MOCK_TX],
        pagination: { total: 1, page: 1, limit: 20, total_pages: 1 },
      },
    });
    mockMutation.mockReturnValue({ mutateAsync: jest.fn(), isPending: false });
    render(<HistoryPage />);
    expect(screen.getByText('test.wav')).toBeInTheDocument();
    expect(screen.getByText('completed')).toBeInTheDocument();
    expect(screen.getByText(/30\.5 秒/)).toBeInTheDocument();
  });

  test('"進入校正" button visible for completed transcriptions', () => {
    mockQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        items: [MOCK_TX],
        pagination: { total: 1, page: 1, limit: 20, total_pages: 1 },
      },
    });
    mockMutation.mockReturnValue({ mutateAsync: jest.fn(), isPending: false });
    render(<HistoryPage />);
    expect(screen.getByRole('button', { name: /進入校正/ })).toBeInTheDocument();
  });

  test('"進入校正" not shown for non-completed transcriptions', () => {
    mockQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        items: [{ ...MOCK_TX, status: 'processing' }],
        pagination: { total: 1, page: 1, limit: 20, total_pages: 1 },
      },
    });
    mockMutation.mockReturnValue({ mutateAsync: jest.fn(), isPending: false });
    render(<HistoryPage />);
    expect(screen.queryByRole('button', { name: /進入校正/ })).not.toBeInTheDocument();
  });

  test('clicking "進入校正" calls mutation + router.push', async () => {
    const mockMutateAsync = jest.fn().mockResolvedValueOnce({ id: 5 });
    mockQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        items: [MOCK_TX],
        pagination: { total: 1, page: 1, limit: 20, total_pages: 1 },
      },
    });
    mockMutation.mockReturnValue({ mutateAsync: mockMutateAsync, isPending: false });
    render(<HistoryPage />);

    await userEvent.click(screen.getByRole('button', { name: /進入校正/ }));

    expect(mockMutateAsync).toHaveBeenCalledWith({ transcription_id: 7 });
    expect(mockPush).toHaveBeenCalledWith('/correction/5');
  });
});
