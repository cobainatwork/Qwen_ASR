import { InputHTMLAttributes, forwardRef } from 'react';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, className = '', ...rest }, ref) => (
    <div className="flex flex-col gap-1">
      {label && <label className="text-sm text-foreground/70">{label}</label>}
      <input
        ref={ref}
        className={`px-3 py-2 rounded-xl bg-glass-50 backdrop-blur-sm border border-white/40 focus:border-accent focus:outline-none ${className}`}
        {...rest}
      />
      {error && <span className="text-sm text-red-500">{error}</span>}
    </div>
  )
);
Input.displayName = 'Input';
