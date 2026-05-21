import { render, screen } from '@testing-library/react';
import { CorrectionLayout } from '@/components/correction/CorrectionLayout';

describe('CorrectionLayout', () => {
  it('renders 3 panels with correct widths', () => {
    render(
      <CorrectionLayout
        audioPanel={<div data-testid="audio">audio</div>}
        listPanel={<div data-testid="list">list</div>}
        editorPanel={<div data-testid="editor">editor</div>}
      />,
    );
    expect(screen.getByTestId('audio')).toBeInTheDocument();
    expect(screen.getByTestId('list')).toBeInTheDocument();
    expect(screen.getByTestId('editor')).toBeInTheDocument();
  });

  it('renders aside elements with correct ARIA labels', () => {
    render(
      <CorrectionLayout
        audioPanel={<div>audio</div>}
        listPanel={<div>list</div>}
        editorPanel={<div>editor</div>}
      />,
    );
    expect(screen.getByRole('complementary', { name: '音訊區' })).toBeInTheDocument();
    expect(screen.getByRole('complementary', { name: '段落清單' })).toBeInTheDocument();
    expect(screen.getByRole('main', { name: '文字編輯區' })).toBeInTheDocument();
  });

  it('renders toolbar when provided', () => {
    render(
      <CorrectionLayout
        audioPanel={<div>audio</div>}
        listPanel={<div>list</div>}
        editorPanel={<div>editor</div>}
        toolbar={<div data-testid="toolbar">toolbar</div>}
      />,
    );
    expect(screen.getByTestId('toolbar')).toBeInTheDocument();
  });

  it('does not render toolbar wrapper when toolbar is not provided', () => {
    render(
      <CorrectionLayout
        audioPanel={<div>audio</div>}
        listPanel={<div>list</div>}
        editorPanel={<div>editor</div>}
      />,
    );
    expect(screen.queryByRole('toolbar')).not.toBeInTheDocument();
  });
});
