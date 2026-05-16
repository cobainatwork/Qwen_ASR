import { render, screen, act } from '@testing-library/react';

import { AuthProvider } from '@/components/auth/AuthProvider';
import { useAuth } from '@/components/auth/useAuth';

function Probe() {
  const { token, setToken, isAuthenticated } = useAuth();
  return (
    <div>
      <span data-testid="token">{token ?? 'none'}</span>
      <span data-testid="auth">{isAuthenticated ? 'yes' : 'no'}</span>
      <button onClick={() => setToken('abc')}>set</button>
      <button onClick={() => setToken(null)}>clear</button>
    </div>
  );
}

describe('AuthProvider', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('starts with no token', () => {
    render(<AuthProvider><Probe /></AuthProvider>);
    expect(screen.getByTestId('token')).toHaveTextContent('none');
    expect(screen.getByTestId('auth')).toHaveTextContent('no');
  });

  it('persists token to localStorage', () => {
    render(<AuthProvider><Probe /></AuthProvider>);
    act(() => {
      screen.getByText('set').click();
    });
    expect(screen.getByTestId('token')).toHaveTextContent('abc');
    expect(localStorage.getItem('qwen-asr-token')).toBe('abc');
  });

  it('clears token on null', () => {
    localStorage.setItem('qwen-asr-token', 'preloaded');
    render(<AuthProvider><Probe /></AuthProvider>);
    act(() => {
      screen.getByText('clear').click();
    });
    expect(screen.getByTestId('token')).toHaveTextContent('none');
    expect(localStorage.getItem('qwen-asr-token')).toBeNull();
  });
});
