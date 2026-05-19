import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['var(--font-inter)', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
      colors: {
        // CSS 變數對應（允許 @apply text-foreground / bg-background）
        foreground: 'var(--foreground)',
        background: 'var(--background)',
        // Apple Glassmorphism palette
        glass: {
          50: 'rgba(255, 255, 255, 0.6)',
          100: 'rgba(255, 255, 255, 0.4)',
          200: 'rgba(255, 255, 255, 0.2)',
        },
        accent: {
          DEFAULT: '#007AFF', // Apple blue
          hover: '#0051D5',
        },
        surface: {
          DEFAULT: '#F2F2F7', // Apple light gray
          dark: '#1C1C1E',
        },
      },
      backdropBlur: {
        xs: '2px',
        sm: '6px',
        md: '12px',
        lg: '24px',
      },
      borderRadius: {
        xl: '16px',
        '2xl': '24px',
      },
      boxShadow: {
        soft: '0 4px 24px rgba(0, 0, 0, 0.08)',
        glass: '0 8px 32px rgba(0, 0, 0, 0.06)',
      },
    },
  },
  plugins: [],
};

export default config;
