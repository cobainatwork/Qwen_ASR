import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { Button } from '@/components/ui/Button';

describe('Button', () => {
  it('renders primary by default', () => {
    render(<Button>Submit</Button>);
    const btn = screen.getByRole('button', { name: 'Submit' });
    expect(btn).toHaveClass('btn-primary');
  });

  it('renders secondary variant', () => {
    render(<Button variant="secondary">Cancel</Button>);
    expect(screen.getByRole('button', { name: 'Cancel' })).toHaveClass('btn-secondary');
  });

  it('calls onClick handler', async () => {
    const handler = jest.fn();
    render(<Button onClick={handler}>Click</Button>);
    await userEvent.click(screen.getByRole('button'));
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it('respects disabled prop', () => {
    render(<Button disabled>Disabled</Button>);
    expect(screen.getByRole('button')).toBeDisabled();
  });
});
