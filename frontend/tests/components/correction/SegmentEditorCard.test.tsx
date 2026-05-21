import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SegmentEditorCard } from '@/components/correction/editor/SegmentEditorCard';
import { useCorrectionStore } from '@/stores/correctionStore';

const segment = {
  id: 1,
  segment_index: 0,
  start_sec: 0,
  end_sec: 1,
  original_text: '原文',
  corrected_text: '校正',
  speaker_label: 'S0',
  is_skipped: false,
  version: 1,
  session_id: 1,
  updated_at: '',
} as any;

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient();
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

beforeEach(() => useCorrectionStore.setState(useCorrectionStore.getInitialState(), true));

describe('SegmentEditorCard', () => {
  it('顯示原文 + 編輯文字 + diff 高亮', () => {
    render(wrap(<SegmentEditorCard segment={segment} />));
    // original-text div 有 data-testid；DiffText 亦會含原文但以 delete span 呈現
    expect(screen.getByTestId('original-text')).toHaveTextContent('原文');
    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
    expect(textarea.value).toBe('校正');
  });

  it('編輯文字觸發 setDraft', async () => {
    render(wrap(<SegmentEditorCard segment={segment} />));
    const textarea = screen.getByRole('textbox');
    await userEvent.clear(textarea);
    await userEvent.type(textarea, 'new');
    const draft = useCorrectionStore.getState().draftMap.get(1);
    expect(draft?.text).toBe('new');
    expect(useCorrectionStore.getState().saveStates.get(1)).toBe('unsaved');
  });

  it('focused 時進入聚焦模式 class', () => {
    useCorrectionStore.getState().setFocused(1);
    useCorrectionStore.getState().toggleFocusMode();
    render(wrap(<SegmentEditorCard segment={segment} />));
    const card = screen.getByRole('article');
    expect(card.className).toMatch(/focused/);
  });
});
