import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';

jest.mock('next/navigation', () => ({
  usePathname: () => '/',
}));

jest.mock('next/link', () => {
  const React = require('react');
  return function MockLink({ href, children, className }: { href: string; children: React.ReactNode; className?: string }) {
    return React.createElement('a', { href, className }, children);
  };
});

import { AppShell } from '@/components/layout/AppShell';

describe('<AppShell />', () => {
  test('renders banner, navigation, and main landmarks', () => {
    render(
      <AppShell>
        <p>page-content</p>
      </AppShell>,
    );

    expect(screen.getByRole('banner')).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: /主選單/ })).toBeInTheDocument();
    expect(screen.getByRole('main')).toBeInTheDocument();
  });

  test('mounts children into the main landmark', () => {
    render(
      <AppShell>
        <p data-testid="child">hello</p>
      </AppShell>,
    );

    const main = screen.getByRole('main');
    expect(main).toContainElement(screen.getByTestId('child'));
  });

  test('main slot uses app-main flex class for viewport-fill behaviour', () => {
    render(<AppShell>x</AppShell>);
    expect(screen.getByRole('main')).toHaveClass('app-main');
  });
});
