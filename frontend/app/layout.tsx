import './globals.css';

import { AuthProvider } from '@/components/auth/AuthProvider';
import { Header } from '@/components/layout/Header';

export const metadata = {
  title: 'Qwen3-ASR',
  description: '離線語音辨識平台',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-Hant">
      <body>
        <AuthProvider>
          <Header />
          <main className="mx-4 mt-6">{children}</main>
        </AuthProvider>
      </body>
    </html>
  );
}
