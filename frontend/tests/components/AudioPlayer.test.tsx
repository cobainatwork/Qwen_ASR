import { render, screen } from '@testing-library/react';

import { AudioPlayer } from '@/components/asr/AudioPlayer';

describe('AudioPlayer', () => {
  it('渲染播放按鈕、速度選單、音量 slider', () => {
    render(<AudioPlayer audioUrl={null} speakers={null} onTimeUpdate={() => {}} />);
    expect(screen.getByRole('button', { name: /播放|暫停/ })).toBeInTheDocument();
    expect(screen.getByLabelText('播放速度')).toBeInTheDocument();
    expect(screen.getByLabelText('音量')).toBeInTheDocument();
  });

  it('沒 audioUrl 時播放按鈕 disabled', () => {
    render(<AudioPlayer audioUrl={null} speakers={null} onTimeUpdate={() => {}} />);
    expect(screen.getByRole('button', { name: /播放/ })).toBeDisabled();
  });

  it('速度下拉預設 1x', () => {
    render(<AudioPlayer audioUrl={null} speakers={null} onTimeUpdate={() => {}} />);
    const sel = screen.getByLabelText('播放速度') as HTMLSelectElement;
    expect(sel.value).toBe('1');
  });
});
