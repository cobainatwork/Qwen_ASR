import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SegmentList } from '@/components/correction/list/SegmentList';
import { useCorrectionStore } from '@/stores/correctionStore';

const segments = [
  { id: 1, segment_index: 0, start_sec: 0, end_sec: 1, original_text: '原文一', corrected_text: '校正一', speaker_label: 'S0', is_skipped: false, version: 1, session_id: 1, updated_at: '' } as any,
  { id: 2, segment_index: 1, start_sec: 1, end_sec: 2, original_text: '原文二', corrected_text: null, speaker_label: 'S1', is_skipped: false, version: 1, session_id: 1, updated_at: '' } as any,
  { id: 3, segment_index: 2, start_sec: 2, end_sec: 3, original_text: '原文三', corrected_text: null, speaker_label: 'S0', is_skipped: true, version: 1, session_id: 1, updated_at: '' } as any,
];

beforeEach(() => useCorrectionStore.setState(useCorrectionStore.getInitialState(), true));

describe('SegmentList', () => {
  it('預設顯示三段', () => {
    render(<SegmentList segments={segments} />);
    expect(screen.getAllByRole('listitem')).toHaveLength(3);
  });

  it('搜尋 substring 過濾', async () => {
    render(<SegmentList segments={segments} />);
    const input = screen.getByLabelText('搜尋');
    await userEvent.type(input, '校正');
    expect(screen.getAllByRole('listitem')).toHaveLength(1);
  });

  it('依語者篩選', async () => {
    render(<SegmentList segments={segments} />);
    await userEvent.selectOptions(screen.getByLabelText('依語者'), 'S1');
    expect(screen.getAllByRole('listitem')).toHaveLength(1);
  });

  it('依狀態篩選：skipped', async () => {
    render(<SegmentList segments={segments} />);
    await userEvent.selectOptions(screen.getByLabelText('依狀態'), 'skipped');
    expect(screen.getAllByRole('listitem')).toHaveLength(1);
  });

  it('點選段落 → setFocused', async () => {
    render(<SegmentList segments={segments} />);
    await userEvent.click(screen.getByText('#0'));
    expect(useCorrectionStore.getState().focusedSegmentId).toBe(1);
  });
});
