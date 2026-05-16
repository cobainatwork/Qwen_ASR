import { ButtonHTMLAttributes, ReactNode } from 'react';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary';
  children: ReactNode;
}

export function Button({ variant = 'primary', children, className = '', ...rest }: ButtonProps) {
  const base = variant === 'primary' ? 'btn-primary' : 'btn-secondary';
  return (
    <button className={`${base} ${className}`} {...rest}>
      {children}
    </button>
  );
}
