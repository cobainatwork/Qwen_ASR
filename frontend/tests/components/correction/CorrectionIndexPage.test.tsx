import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';

// Mock TanStack Query hook — test only the render layer.
jest.mock('@/lib/api/correction', () => ({
  useCorrectionSessionsListQuery: jest.fn(),
}));

// Mock next/link
jest.mock('next/link', () => {
  const React = require('react');
  return function MockLink({
    href,
    children,
    className,
  }: {
    href: string;
    children: React.ReactNode;
    className?: string;
  }) {
    return React.createElement('a', { href, className }, children);
  };
});

// Import after mocks are registered at module level so React singleton is stable.
import CorrectionIndexPage from '@/app/correction/page';
import { useCorrectionSessionsListQuery } from '@/lib/api/correction';

const mockQuery = useCorrectionSessionsListQuery as jest.Mock;

describe('CorrectionIndexPage', () => {
  afterEach(() => {
    jest.clearAllMocks();
  });

  test('shows loading state', () => {
    mockQuery.mockReturnValue({ isLoading: true, isError: false, data: undefined });
    render(<CorrectionIndexPage />);
    expect(screen.getByText(/載入中/)).toBeInTheDocument();
  });

  test('shows error state', () => {
    mockQuery.mockReturnValue({ isLoading: false, isError: true, data: undefined });
    render(<CorrectionIndexPage />);
    expect(screen.getByText(/載入失敗/)).toBeInTheDocument();
  });

  test('shows empty state when no sessions', () => {
    mockQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [], pagination: { total: 0, page: 1, limit: 20, total_pages: 1 } },
    });
    render(<CorrectionIndexPage />);
    expect(screen.getByText(/目前沒有校正工作階段/)).toBeInTheDocument();
  });

  test('renders session rows with links to /correction/{id}', () => {
    mockQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        items: [
          {
            id: 42,
            name: 'Test Session',
            status: 'in_progress',
            created_at: '2026-05-01T10:00:00Z',
            updated_at: '2026-05-02T12:00:00Z',
            transcription_id: 1,
            audio_file_id: null,
          },
        ],
        pagination: { total: 1, page: 1, limit: 20, total_pages: 1 },
      },
    });
    render(<CorrectionIndexPage />);
    expect(screen.getByText('Test Session')).toBeInTheDocument();
    expect(screen.getByText('in_progress')).toBeInTheDocument();
    const link = screen.getByRole('link', { name: /開啟/ });
    expect(link).toHaveAttribute('href', '/correction/42');
  });

  test('renders accessible table with caption', () => {
    mockQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        items: [
          {
            id: 1,
            name: 'S1',
            status: 'completed',
            created_at: '2026-05-01T00:00:00Z',
            updated_at: '2026-05-01T00:00:00Z',
            transcription_id: 1,
            audio_file_id: null,
          },
        ],
        pagination: { total: 1, page: 1, limit: 20, total_pages: 1 },
      },
    });
    render(<CorrectionIndexPage />);
    expect(screen.getByRole('table')).toBeInTheDocument();
    // sr-only caption is still in the DOM
    expect(screen.getByText('校正工作階段列表')).toBeInTheDocument();
  });
});
