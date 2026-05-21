import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { CorrectionToolbar } from '@/components/correction/CorrectionToolbar';
import { useCorrectionStore } from '@/stores/correctionStore';

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

beforeEach(() => useCorrectionStore.setState(useCorrectionStore.getInitialState(), true));

describe('CorrectionToolbar', () => {
  it('renders 4 buttons', () => {
    render(wrap(<CorrectionToolbar sessionId={1} />));
    expect(screen.getByRole('button', { name: /全部儲存/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /匯出 JSONL/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /匯出 Excel/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /品質評估/ })).toBeInTheDocument();
  });

  it('export buttons are enabled when no unsaved changes', () => {
    render(wrap(<CorrectionToolbar sessionId={1} />));
    expect(screen.getByRole('button', { name: /匯出 JSONL/ })).not.toBeDisabled();
    expect(screen.getByRole('button', { name: /匯出 Excel/ })).not.toBeDisabled();
    expect(screen.getByRole('button', { name: /品質評估/ })).not.toBeDisabled();
  });
});
