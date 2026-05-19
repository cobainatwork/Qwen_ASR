import './globals.css';
import { Inter } from 'next/font/google';

import { AuthProvider } from '@/components/auth/AuthProvider';
import { Header } from '@/components/layout/Header';

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
  weight: ['300', '400', '500', '600', '700'],
  display: 'swap',
});

export const metadata = {
  title: 'Qwen3-ASR',
  description: '離線語音辨識平台',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-Hant" className={inter.variable}>
      <body className="font-sans">
        <AuthProvider>
          <Header />
          <main className="mx-4 mt-6">{children}</main>
        </AuthProvider>
      </body>
    </html>
  );
}
