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

describe('<Sidebar />', () => {
  const originalProfile = process.env.NEXT_PUBLIC_DEPLOYMENT_PROFILE;

  afterEach(() => {
    process.env.NEXT_PUBLIC_DEPLOYMENT_PROFILE = originalProfile;
    jest.resetModules();
  });

  test('always renders 辨識 / 辨識歷史 / 質檢管理 / API 金鑰 nav links', () => {
    process.env.NEXT_PUBLIC_DEPLOYMENT_PROFILE = 'client';
    const { Sidebar } = require('@/components/layout/Sidebar');
    render(<Sidebar />);

    expect(screen.getByRole('link', { name: /離線辨識/ })).toHaveAttribute('href', '/');
    expect(screen.getByRole('link', { name: /辨識歷史/ })).toHaveAttribute('href', '/history');
    expect(screen.getByRole('link', { name: /質檢管理/ })).toHaveAttribute('href', '/quality');
    expect(screen.getByRole('link', { name: /API 金鑰/ })).toHaveAttribute('href', '/keys');
  });

  test('hides Fine-tune submenu in client profile', () => {
    process.env.NEXT_PUBLIC_DEPLOYMENT_PROFILE = 'client';
    const { Sidebar } = require('@/components/layout/Sidebar');
    render(<Sidebar />);

    expect(screen.queryByRole('link', { name: /校正工作台/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /資料集管理/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /訓練管理/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Hotword/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /YouTube/ })).not.toBeInTheDocument();
  });

  test('shows Fine-tune submenu in vendor profile', () => {
    process.env.NEXT_PUBLIC_DEPLOYMENT_PROFILE = 'vendor';
    const { Sidebar } = require('@/components/layout/Sidebar');
    render(<Sidebar />);

    expect(screen.getByRole('link', { name: /校正工作台/ })).toHaveAttribute('href', '/finetune/correction');
    expect(screen.getByRole('link', { name: /資料集管理/ })).toHaveAttribute('href', '/finetune/datasets');
    expect(screen.getByRole('link', { name: /訓練管理/ })).toHaveAttribute('href', '/finetune/training');
    expect(screen.getByRole('link', { name: /Hotword/ })).toHaveAttribute('href', '/finetune/hotwords');
    expect(screen.getByRole('link', { name: /YouTube/ })).toHaveAttribute('href', '/youtube');
  });

  test('exposes a <nav> landmark with aria-label', () => {
    const { Sidebar } = require('@/components/layout/Sidebar');
    render(<Sidebar />);
    expect(screen.getByRole('navigation', { name: /主選單/ })).toBeInTheDocument();
  });
});
