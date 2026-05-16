# Phase 2 / M6 — 前端 scaffolding（Next.js 14 + Tailwind）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 Next.js 14 + Tailwind + Apple Glassmorphism 設計系統的前端骨架，含 typed API client、auth provider、3 個核心頁面（辨識 / 歷史 / API 金鑰），完成後可在瀏覽器上傳音檔取得 transcribe 結果。

**Architecture:** App Router（不用 Pages Router）。`lib/api/client.ts` 透過 `openapi-typescript` 從 backend `/openapi.json` 生成 type。Auth 透過 React Context + localStorage，所有 API 呼叫自動附 Bearer header。Apple Glassmorphism 透過 Tailwind 自訂 utility 與 backdrop-filter 實現。

**Tech Stack:** Next.js 14（App Router）、React 18、TypeScript 5、Tailwind CSS 3、SWR、Jest 29 + React Testing Library 14、Playwright 1（M9 啟用，本 milestone 僅安裝）。

**對應設計文件：** Phase 2 design.md §3.2、§2.3。對應規格：v1.9 §4。

---

## File Structure

| 路徑 | 動作 | 責任 |
|------|------|------|
| `frontend/package.json` | Create | 依賴清單 |
| `frontend/tsconfig.json` | Create | TS 配置 |
| `frontend/next.config.mjs` | Create | Next.js 配置（含 backend proxy） |
| `frontend/tailwind.config.ts` | Create | Tailwind + Apple 設計系統 token |
| `frontend/postcss.config.mjs` | Create | PostCSS |
| `frontend/.eslintrc.json` | Create | ESLint Next.js + TS 配置 |
| `frontend/jest.config.ts` | Create | Jest 配置 |
| `frontend/jest.setup.ts` | Create | Testing Library 全域設定 |
| `frontend/playwright.config.ts` | Create | Playwright 配置（M9 啟用） |
| `frontend/app/layout.tsx` | Create | 根 layout |
| `frontend/app/page.tsx` | Create | 首頁辨識 |
| `frontend/app/history/page.tsx` | Create | 歷史紀錄 |
| `frontend/app/keys/page.tsx` | Create | API 金鑰管理 |
| `frontend/app/globals.css` | Create | Tailwind base + 全域 style |
| `frontend/components/ui/Button.tsx` | Create | UI Kit |
| `frontend/components/ui/Card.tsx` | Create | UI Kit |
| `frontend/components/ui/Input.tsx` | Create | UI Kit |
| `frontend/components/ui/Modal.tsx` | Create | UI Kit |
| `frontend/components/layout/Header.tsx` | Create | 共用 header |
| `frontend/components/auth/AuthProvider.tsx` | Create | React Context |
| `frontend/components/auth/useAuth.ts` | Create | hook |
| `frontend/components/asr/AudioUploader.tsx` | Create | 首頁主元件 |
| `frontend/components/asr/TranscriptionResult.tsx` | Create | 結果顯示 |
| `frontend/lib/api/client.ts` | Create | typed fetch wrapper |
| `frontend/lib/api/types.ts` | Create | 從 openapi 生成（佔位，scripts/generate-api.ts 產生實際內容） |
| `frontend/scripts/generate-api.ts` | Create | openapi-typescript 執行腳本 |
| `frontend/tests/components/Button.test.tsx` | Create | UI Kit 測試 |
| `frontend/tests/components/AuthProvider.test.tsx` | Create | Auth 測試 |
| `frontend/tests/components/AudioUploader.test.tsx` | Create | 上傳元件測試 |
| `frontend/.gitignore` | Create | Node 排除（node_modules / .next 等） |
| `.gitignore` | Modify | 補 `frontend/.next/` / `frontend/node_modules/` |
| `docker-compose.yml` | Modify | 加 frontend service（可選，預設不啟用） |

---

## Task 6.1：Next.js 專案初始化 + 配置檔

**Files:**
- Create: 全部 frontend 根目錄配置檔（package.json / tsconfig.json / next.config.mjs / tailwind.config.ts / postcss.config.mjs / .eslintrc.json / .gitignore）

- [ ] **Step 1：建立 frontend 目錄**

```powershell
cd D:\Qwen_asr
New-Item frontend -ItemType Directory -Force
cd frontend
```

- [ ] **Step 2：撰寫 `package.json`**

```json
{
  "name": "qwen-asr-frontend",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint",
    "typecheck": "tsc --noEmit",
    "test": "jest",
    "test:watch": "jest --watch",
    "test:e2e": "playwright test",
    "generate-api": "tsx scripts/generate-api.ts"
  },
  "dependencies": {
    "next": "14.2.18",
    "react": "18.3.1",
    "react-dom": "18.3.1",
    "swr": "2.2.5"
  },
  "devDependencies": {
    "@playwright/test": "1.48.0",
    "@testing-library/jest-dom": "6.5.0",
    "@testing-library/react": "16.0.1",
    "@testing-library/user-event": "14.5.2",
    "@types/jest": "29.5.13",
    "@types/node": "22.7.4",
    "@types/react": "18.3.11",
    "@types/react-dom": "18.3.0",
    "autoprefixer": "10.4.20",
    "eslint": "8.57.1",
    "eslint-config-next": "14.2.18",
    "jest": "29.7.0",
    "jest-environment-jsdom": "29.7.0",
    "openapi-typescript": "7.4.1",
    "postcss": "8.4.47",
    "tailwindcss": "3.4.13",
    "tsx": "4.19.1",
    "typescript": "5.6.2"
  }
}
```

- [ ] **Step 3：撰寫 `tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "baseUrl": ".",
    "paths": {
      "@/*": ["./*"]
    }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

- [ ] **Step 4：撰寫 `next.config.mjs`**

```javascript
/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${process.env.BACKEND_BASE_URL || 'http://localhost:8000'}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
```

- [ ] **Step 5：撰寫 `tailwind.config.ts`**

```typescript
import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
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
```

- [ ] **Step 6：撰寫 `postcss.config.mjs`**

```javascript
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

- [ ] **Step 7：撰寫 `.eslintrc.json`**

```json
{
  "extends": ["next/core-web-vitals", "next/typescript"],
  "rules": {
    "@typescript-eslint/no-unused-vars": ["error", { "argsIgnorePattern": "^_" }]
  }
}
```

- [ ] **Step 8：撰寫 `frontend/.gitignore`**

```
node_modules/
.next/
out/
.DS_Store
*.log
.env.local
.env.production
coverage/
playwright-report/
test-results/
next-env.d.ts
```

- [ ] **Step 9：補根目錄 `.gitignore`（frontend artifacts）**

讀根目錄 `.gitignore` 確認是否已含 `frontend/.next/` / `frontend/node_modules/`。若無，在 `# Node.js` 區塊補：

```
frontend/node_modules/
frontend/.next/
frontend/out/
frontend/coverage/
```

- [ ] **Step 10：安裝依賴**

```powershell
cd D:\Qwen_asr\frontend
npm install
```

預期：成功安裝，無 vulnerability error（warning 可接受）。

- [ ] **Step 11：驗證 `next build` 可執行（即使無 page 也應通過）**

先建立最小 `app/page.tsx` 與 `app/layout.tsx`（後續 Task 會覆蓋）：

```powershell
New-Item app -ItemType Directory -Force
@"
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-Hant">
      <body>{children}</body>
    </html>
  );
}
"@ | Out-File -Encoding utf8 app/layout.tsx -NoNewline

@"
export default function Page() {
  return <main>placeholder</main>;
}
"@ | Out-File -Encoding utf8 app/page.tsx -NoNewline

npm run typecheck
npm run build
```

預期：`typecheck` 通過、`build` 成功（產出 `.next/`）。

- [ ] **Step 12：Commit**

```powershell
cd D:\Qwen_asr
git add frontend/.gitignore frontend/package.json frontend/package-lock.json frontend/tsconfig.json frontend/next.config.mjs frontend/tailwind.config.ts frontend/postcss.config.mjs frontend/.eslintrc.json frontend/app .gitignore
git status
git commit -m "$(@'
feat(m6): Next.js 14 frontend scaffolding 初始化

- package.json：Next 14.2 / React 18.3 / TS 5.6 / Tailwind 3.4 / Jest 29 / Playwright 1.48
- tsconfig.json：strict mode + paths alias @/*
- next.config.mjs：BACKEND_BASE_URL proxy rewrite /api/* → backend
- tailwind.config.ts：Apple Glassmorphism palette（glass / accent / surface）+ backdrop-blur + soft shadow
- .eslintrc.json：next + typescript 規則
- 補根目錄 .gitignore（frontend/.next/ / node_modules/ / out/ / coverage/）
- 占位 app/layout.tsx 與 app/page.tsx（T6.5 覆蓋）
- npm run build 通過

對應計劃：M6 Task 6.1
對應設計：Phase 2 design.md §3.2 / §2.3

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
'@)"
```

注意：commit 含 `package-lock.json`（大檔但屬必需 lockfile）。

---

## Task 6.2：UI Kit + 設計系統元件

**Files:**
- Create: `frontend/app/globals.css`
- Create: `frontend/components/ui/Button.tsx`
- Create: `frontend/components/ui/Card.tsx`
- Create: `frontend/components/ui/Input.tsx`
- Create: `frontend/components/ui/Modal.tsx`
- Create: `frontend/components/layout/Header.tsx`

- [ ] **Step 1：撰寫 `app/globals.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --background: #f2f2f7;
  --foreground: #1c1c1e;
}

@media (prefers-color-scheme: dark) {
  :root {
    --background: #1c1c1e;
    --foreground: #f2f2f7;
  }
}

html, body {
  background-color: var(--background);
  color: var(--foreground);
  -webkit-font-smoothing: antialiased;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

@layer components {
  .glass-card {
    @apply bg-glass-50 backdrop-blur-md rounded-2xl shadow-glass border border-white/30;
  }
  .btn-primary {
    @apply bg-accent text-white px-4 py-2 rounded-xl shadow-soft hover:bg-accent-hover transition-colors;
  }
  .btn-secondary {
    @apply bg-glass-100 backdrop-blur-sm text-foreground px-4 py-2 rounded-xl border border-white/40 hover:bg-glass-50 transition-colors;
  }
}
```

- [ ] **Step 2：撰寫 `components/ui/Button.tsx`**

```tsx
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
```

- [ ] **Step 3：撰寫 `components/ui/Card.tsx`**

```tsx
import { HTMLAttributes, ReactNode } from 'react';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
}

export function Card({ children, className = '', ...rest }: CardProps) {
  return (
    <div className={`glass-card p-6 ${className}`} {...rest}>
      {children}
    </div>
  );
}
```

- [ ] **Step 4：撰寫 `components/ui/Input.tsx`**

```tsx
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
```

- [ ] **Step 5：撰寫 `components/ui/Modal.tsx`**

```tsx
import { ReactNode, useEffect } from 'react';

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
}

export function Modal({ open, onClose, title, children }: ModalProps) {
  useEffect(() => {
    if (!open) return;
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onEsc);
    return () => document.removeEventListener('keydown', onEsc);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="glass-card max-w-lg w-full mx-4 p-6"
        onClick={(e) => e.stopPropagation()}
      >
        {title && <h2 className="text-xl font-semibold mb-4">{title}</h2>}
        {children}
      </div>
    </div>
  );
}
```

- [ ] **Step 6：撰寫 `components/layout/Header.tsx`**

```tsx
import Link from 'next/link';

export function Header() {
  return (
    <header className="glass-card mx-4 mt-4 px-6 py-4 flex items-center justify-between">
      <Link href="/" className="text-xl font-semibold">Qwen3-ASR</Link>
      <nav className="flex gap-4 text-sm">
        <Link href="/" className="hover:text-accent">辨識</Link>
        <Link href="/history" className="hover:text-accent">歷史</Link>
        <Link href="/keys" className="hover:text-accent">金鑰</Link>
      </nav>
    </header>
  );
}
```

- [ ] **Step 7：執行 typecheck + lint**

```powershell
cd D:\Qwen_asr\frontend
npm run typecheck
npm run lint
```

預期：通過。

- [ ] **Step 8：Commit**

```powershell
cd D:\Qwen_asr
git add frontend/app/globals.css frontend/components/ui frontend/components/layout
git commit -m "$(@'
feat(m6): UI Kit + Apple Glassmorphism 設計系統元件

- app/globals.css：Tailwind base + glass-card / btn-primary / btn-secondary utility
- components/ui/Button.tsx：variant primary / secondary
- components/ui/Card.tsx：glass-card 包裝
- components/ui/Input.tsx：含 label / error 顯示，forwardRef 支援 react-hook-form
- components/ui/Modal.tsx：含 ESC 關閉、backdrop click 關閉、aria-modal
- components/layout/Header.tsx：3 個 nav link（辨識 / 歷史 / 金鑰）

對應計劃：M6 Task 6.2
對應設計：規格 v1.9 §4.2 Apple 圓滑風格

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
'@)"
```

---

## Task 6.3：API client + typed types 自動生成

**Files:**
- Create: `frontend/lib/api/client.ts`
- Create: `frontend/lib/api/types.ts`（初始空，由 script 寫入）
- Create: `frontend/scripts/generate-api.ts`

- [ ] **Step 1：撰寫 `frontend/scripts/generate-api.ts`**

```typescript
import openapiTS, { astToString } from 'openapi-typescript';
import { writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const BACKEND = process.env.BACKEND_BASE_URL ?? 'http://localhost:8000';
const OUTPUT = resolve(__dirname, '../lib/api/types.ts');

async function main() {
  const ast = await openapiTS(new URL('/openapi.json', BACKEND));
  const content = `// Auto-generated from ${BACKEND}/openapi.json. Do not edit.\n\n${astToString(ast)}`;
  await writeFile(OUTPUT, content, 'utf-8');
  console.log(`Generated ${OUTPUT}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
```

- [ ] **Step 2：撰寫 `frontend/lib/api/types.ts`（初始占位）**

```typescript
// Auto-generated placeholder. Run `npm run generate-api` against running backend to populate.

export interface paths {}
export interface components {
  schemas: Record<string, unknown>;
}

// Phase 2 / M6 manual types（在 generate-api 跑前提供基本型別）
export interface ResponseEnvelope<T> {
  success: boolean;
  data: T | null;
  error: { code: string; message: string; details?: Record<string, unknown> } | null;
}

export interface TranscribeOptions {
  language?: string;
  return_timestamps?: boolean;
}

export interface TranscribeData {
  transcription_id: number;
  audio_file_id: number;
  text: string;
  duration_sec: number;
  processing_duration_sec: number;
  model_version: string;
  resampling_warning: boolean;
  vad_segments_count: number;
  warnings: string[];
}
```

- [ ] **Step 3：撰寫 `frontend/lib/api/client.ts`**

```typescript
import type { ResponseEnvelope, TranscribeData } from './types';

const DEFAULT_TIMEOUT_MS = 1200_000; // 對齊 backend ASR_REQUEST_TIMEOUT_SEC

interface ApiClientOptions {
  baseUrl?: string;
  getToken?: () => string | null;
}

export class ApiError extends Error {
  constructor(public code: string, message: string, public status: number) {
    super(message);
    this.name = 'ApiError';
  }
}

export class ApiClient {
  private baseUrl: string;
  private getToken: () => string | null;

  constructor(options: ApiClientOptions = {}) {
    this.baseUrl = options.baseUrl ?? '';
    this.getToken = options.getToken ?? (() => null);
  }

  async transcribe(file: File, options: { language?: string; return_timestamps?: boolean } = {}): Promise<TranscribeData> {
    const form = new FormData();
    form.append('file', file);
    form.append('options_json', JSON.stringify(options));

    const body = await this.request<TranscribeData>('/api/v1/asr/transcribe', {
      method: 'POST',
      body: form,
    });
    return body;
  }

  private async request<T>(path: string, init: RequestInit): Promise<T> {
    const token = this.getToken();
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);

    try {
      const resp = await fetch(`${this.baseUrl}${path}`, {
        ...init,
        signal: controller.signal,
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...(init.headers ?? {}),
        },
      });
      const json: ResponseEnvelope<T> = await resp.json();
      if (!json.success || json.data === null) {
        throw new ApiError(json.error?.code ?? 'UNKNOWN', json.error?.message ?? 'Request failed', resp.status);
      }
      return json.data;
    } finally {
      clearTimeout(timer);
    }
  }
}
```

- [ ] **Step 4：執行 typecheck**

```powershell
cd D:\Qwen_asr\frontend
npm run typecheck
```

預期：通過。

- [ ] **Step 5：Commit**

```powershell
cd D:\Qwen_asr
git add frontend/lib/api frontend/scripts/generate-api.ts
git commit -m "$(@'
feat(m6): API client + types 自動生成

- lib/api/types.ts：手動 ResponseEnvelope / TranscribeOptions / TranscribeData 占位
  - npm run generate-api 跑 backend openapi.json 後覆寫為完整 typed
- lib/api/client.ts：ApiClient 類別
  - 1200 秒 timeout（對齊 backend ASR_REQUEST_TIMEOUT_SEC）
  - Bearer token 自動附加（getToken hook）
  - ApiError 含 code / message / status
  - transcribe 多 part form 上傳
- scripts/generate-api.ts：openapi-typescript 執行器
  - 讀 BACKEND_BASE_URL env（預設 localhost:8000）
  - 寫入 lib/api/types.ts

對應計劃：M6 Task 6.3

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
'@)"
```

---

## Task 6.4：Auth Provider + useAuth hook

**Files:**
- Create: `frontend/components/auth/AuthProvider.tsx`
- Create: `frontend/components/auth/useAuth.ts`

- [ ] **Step 1：撰寫 `components/auth/AuthProvider.tsx`**

```tsx
'use client';

import { createContext, ReactNode, useCallback, useEffect, useState } from 'react';

const STORAGE_KEY = 'qwen-asr-token';

interface AuthContextValue {
  token: string | null;
  setToken: (token: string | null) => void;
  isAuthenticated: boolean;
}

export const AuthContext = createContext<AuthContextValue>({
  token: null,
  setToken: () => {},
  isAuthenticated: false,
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(null);

  useEffect(() => {
    const stored = typeof window !== 'undefined' ? localStorage.getItem(STORAGE_KEY) : null;
    if (stored) setTokenState(stored);
  }, []);

  const setToken = useCallback((next: string | null) => {
    setTokenState(next);
    if (typeof window === 'undefined') return;
    if (next === null) {
      localStorage.removeItem(STORAGE_KEY);
    } else {
      localStorage.setItem(STORAGE_KEY, next);
    }
  }, []);

  return (
    <AuthContext.Provider value={{ token, setToken, isAuthenticated: token !== null }}>
      {children}
    </AuthContext.Provider>
  );
}
```

- [ ] **Step 2：撰寫 `components/auth/useAuth.ts`**

```typescript
'use client';

import { useContext } from 'react';

import { AuthContext } from './AuthProvider';

export function useAuth() {
  return useContext(AuthContext);
}
```

- [ ] **Step 3：typecheck**

```powershell
cd D:\Qwen_asr\frontend
npm run typecheck
```

預期：通過。

- [ ] **Step 4：Commit**

```powershell
cd D:\Qwen_asr
git add frontend/components/auth
git commit -m "$(@'
feat(m6): Auth Provider + useAuth hook

- components/auth/AuthProvider.tsx：React Context
  - token state 與 localStorage 同步（key: qwen-asr-token）
  - setToken(null) 清除 localStorage
  - SSR safety：useEffect 內讀 localStorage
- components/auth/useAuth.ts：簡單 useContext wrapper

對應計劃：M6 Task 6.4

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
'@)"
```

---

## Task 6.5：3 個核心頁面 + 主要元件

**Files:**
- Modify: `frontend/app/layout.tsx`
- Modify: `frontend/app/page.tsx`
- Create: `frontend/app/history/page.tsx`
- Create: `frontend/app/keys/page.tsx`
- Create: `frontend/components/asr/AudioUploader.tsx`
- Create: `frontend/components/asr/TranscriptionResult.tsx`

- [ ] **Step 1：覆寫 `app/layout.tsx`**

```tsx
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
```

- [ ] **Step 2：撰寫 `components/asr/AudioUploader.tsx`**

```tsx
'use client';

import { useState } from 'react';

import { ApiClient, ApiError } from '@/lib/api/client';
import type { TranscribeData } from '@/lib/api/types';
import { useAuth } from '@/components/auth/useAuth';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';

interface Props {
  onResult: (data: TranscribeData) => void;
}

export function AudioUploader({ onResult }: Props) {
  const { token } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!file) return;
    if (!token) {
      setError('請先在「金鑰」頁設定 API token');
      return;
    }
    setLoading(true);
    setError(null);
    const client = new ApiClient({ getToken: () => token });
    try {
      const data = await client.transcribe(file, { language: 'zh-TW' });
      onResult(data);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`${err.code}: ${err.message}`);
      } else {
        setError(err instanceof Error ? err.message : '未知錯誤');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <h2 className="text-lg font-semibold mb-4">上傳音檔</h2>
      <input
        type="file"
        accept="audio/*,video/*"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        className="mb-4"
        aria-label="選擇音檔"
      />
      <Button onClick={submit} disabled={!file || loading}>
        {loading ? '辨識中...' : '開始辨識'}
      </Button>
      {error && <p className="mt-4 text-red-500 text-sm">{error}</p>}
    </Card>
  );
}
```

- [ ] **Step 3：撰寫 `components/asr/TranscriptionResult.tsx`**

```tsx
import type { TranscribeData } from '@/lib/api/types';
import { Card } from '@/components/ui/Card';

interface Props {
  data: TranscribeData;
}

export function TranscriptionResult({ data }: Props) {
  return (
    <Card className="mt-4">
      <h2 className="text-lg font-semibold mb-4">辨識結果</h2>
      <p className="whitespace-pre-wrap text-base mb-4">{data.text}</p>
      <dl className="grid grid-cols-2 gap-2 text-sm text-foreground/70">
        <dt>音檔長度</dt>
        <dd>{data.duration_sec.toFixed(2)} 秒</dd>
        <dt>處理耗時</dt>
        <dd>{data.processing_duration_sec.toFixed(2)} 秒</dd>
        <dt>模型版本</dt>
        <dd>{data.model_version}</dd>
        <dt>VAD 段落數</dt>
        <dd>{data.vad_segments_count}</dd>
        {data.resampling_warning && (
          <>
            <dt>提示</dt>
            <dd className="text-amber-500">8 kHz 來源已重取樣至 16 kHz</dd>
          </>
        )}
      </dl>
      {data.warnings.length > 0 && (
        <ul className="mt-4 list-disc pl-5 text-sm text-amber-600">
          {data.warnings.map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      )}
    </Card>
  );
}
```

- [ ] **Step 4：覆寫 `app/page.tsx`**

```tsx
'use client';

import { useState } from 'react';

import { AudioUploader } from '@/components/asr/AudioUploader';
import { TranscriptionResult } from '@/components/asr/TranscriptionResult';
import type { TranscribeData } from '@/lib/api/types';

export default function Page() {
  const [result, setResult] = useState<TranscribeData | null>(null);

  return (
    <div className="max-w-2xl mx-auto">
      <AudioUploader onResult={setResult} />
      {result && <TranscriptionResult data={result} />}
    </div>
  );
}
```

- [ ] **Step 5：撰寫 `app/history/page.tsx`**

```tsx
import { Card } from '@/components/ui/Card';

export default function HistoryPage() {
  return (
    <div className="max-w-4xl mx-auto">
      <Card>
        <h2 className="text-lg font-semibold mb-4">歷史紀錄</h2>
        <p className="text-foreground/70 text-sm">
          歷史辨識紀錄將在 M5 補齊端點 GET /api/v1/asr/transcriptions 後接入。
        </p>
      </Card>
    </div>
  );
}
```

- [ ] **Step 6：撰寫 `app/keys/page.tsx`**

```tsx
'use client';

import { useState } from 'react';

import { useAuth } from '@/components/auth/useAuth';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';

export default function KeysPage() {
  const { token, setToken } = useAuth();
  const [input, setInput] = useState('');

  return (
    <div className="max-w-2xl mx-auto">
      <Card>
        <h2 className="text-lg font-semibold mb-4">API 金鑰</h2>
        {token ? (
          <div className="flex flex-col gap-4">
            <p className="text-sm text-foreground/70">
              當前 token：<code className="text-xs">{token.slice(0, 8)}...{token.slice(-4)}</code>
            </p>
            <Button variant="secondary" onClick={() => setToken(null)}>
              清除 token
            </Button>
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            <Input
              label="輸入 bootstrap admin token"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="例如：dev-bootstrap-token"
            />
            <Button onClick={() => { setToken(input); setInput(''); }} disabled={!input}>
              儲存
            </Button>
          </div>
        )}
      </Card>
    </div>
  );
}
```

- [ ] **Step 7：typecheck + lint + build**

```powershell
cd D:\Qwen_asr\frontend
npm run typecheck
npm run lint
npm run build
```

預期：全部通過。

- [ ] **Step 8：Commit**

```powershell
cd D:\Qwen_asr
git add frontend/app frontend/components/asr
git commit -m "$(@'
feat(m6): 3 個核心頁面 + AudioUploader / TranscriptionResult 元件

- app/layout.tsx：AuthProvider + Header + main wrapper
- app/page.tsx（首頁）：AudioUploader + TranscriptionResult
- app/history/page.tsx：歷史紀錄骨架（待 M5 補端點）
- app/keys/page.tsx：API token 輸入 / 清除
- components/asr/AudioUploader.tsx：multipart 上傳 + ApiError 處理
- components/asr/TranscriptionResult.tsx：含 duration / model_version / 8k warning / warnings 列表

驗收：
- typecheck / lint / build 全通過

對應計劃：M6 Task 6.5

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
'@)"
```

---

## Task 6.6：Jest 配置 + 元件測試

**Files:**
- Create: `frontend/jest.config.ts`
- Create: `frontend/jest.setup.ts`
- Create: `frontend/tests/components/Button.test.tsx`
- Create: `frontend/tests/components/AuthProvider.test.tsx`
- Create: `frontend/tests/components/AudioUploader.test.tsx`

- [ ] **Step 1：撰寫 `jest.config.ts`**

```typescript
import type { Config } from 'jest';
import nextJest from 'next/jest';

const createJestConfig = nextJest({
  dir: './',
});

const config: Config = {
  setupFilesAfterEach: ['<rootDir>/jest.setup.ts'],
  testEnvironment: 'jsdom',
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/$1',
  },
  testMatch: ['<rootDir>/tests/**/*.test.{ts,tsx}'],
};

export default createJestConfig(config);
```

- [ ] **Step 2：撰寫 `jest.setup.ts`**

```typescript
import '@testing-library/jest-dom';
```

- [ ] **Step 3：撰寫 `tests/components/Button.test.tsx`**

```tsx
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
```

- [ ] **Step 4：撰寫 `tests/components/AuthProvider.test.tsx`**

```tsx
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
```

- [ ] **Step 5：撰寫 `tests/components/AudioUploader.test.tsx`**

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { AudioUploader } from '@/components/asr/AudioUploader';
import { AuthProvider } from '@/components/auth/AuthProvider';

describe('AudioUploader', () => {
  beforeEach(() => {
    localStorage.clear();
    global.fetch = jest.fn(() =>
      Promise.resolve({
        json: () =>
          Promise.resolve({
            success: true,
            data: {
              transcription_id: 1,
              audio_file_id: 2,
              text: '測試文字',
              duration_sec: 1.0,
              processing_duration_sec: 0.5,
              model_version: 'MOCK',
              resampling_warning: false,
              vad_segments_count: 1,
              warnings: [],
            },
            error: null,
          }),
      }),
    ) as jest.Mock;
  });

  it('shows error if no token', async () => {
    const onResult = jest.fn();
    render(<AuthProvider><AudioUploader onResult={onResult} /></AuthProvider>);

    const file = new File(['fake'], 'a.wav', { type: 'audio/wav' });
    const input = screen.getByLabelText('選擇音檔') as HTMLInputElement;
    await userEvent.upload(input, file);

    await userEvent.click(screen.getByRole('button', { name: '開始辨識' }));

    expect(await screen.findByText(/請先在.*金鑰.*頁設定/)).toBeInTheDocument();
    expect(onResult).not.toHaveBeenCalled();
  });

  it('calls onResult when token present', async () => {
    localStorage.setItem('qwen-asr-token', 'test-token');
    const onResult = jest.fn();
    render(<AuthProvider><AudioUploader onResult={onResult} /></AuthProvider>);

    const file = new File(['fake'], 'a.wav', { type: 'audio/wav' });
    await userEvent.upload(screen.getByLabelText('選擇音檔') as HTMLInputElement, file);
    await userEvent.click(screen.getByRole('button', { name: '開始辨識' }));

    await waitFor(() => expect(onResult).toHaveBeenCalled());
    expect(onResult).toHaveBeenCalledWith(expect.objectContaining({ text: '測試文字' }));
  });
});
```

- [ ] **Step 6：執行測試**

```powershell
cd D:\Qwen_asr\frontend
npm run test
```

預期：4 + 3 + 2 = 9 個測試 PASS。

- [ ] **Step 7：Commit**

```powershell
cd D:\Qwen_asr
git add frontend/jest.config.ts frontend/jest.setup.ts frontend/tests
git commit -m "$(@'
test(m6): Jest + React Testing Library 元件測試（9 個）

- jest.config.ts：next/jest preset + jsdom + @/* path alias
- jest.setup.ts：@testing-library/jest-dom 全域
- tests/components/Button.test.tsx：4 個（variant / click / disabled）
- tests/components/AuthProvider.test.tsx：3 個（初始 / 持久化 / 清除）
- tests/components/AudioUploader.test.tsx：2 個（無 token 拒絕 / 有 token 上傳）
  - global.fetch mock 模擬 backend transcribe 回應

對應計劃：M6 Task 6.6

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
'@)"
```

---

## Task 6.7：CI 補強 + M6 整合驗收

**Files:**
- Modify: `.github/workflows/ci.yml`
- Create: `frontend/playwright.config.ts`（M9 啟用，本 milestone 僅占位）

- [ ] **Step 1：撰寫 `frontend/playwright.config.ts`**

```typescript
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  use: {
    baseURL: process.env.FRONTEND_BASE_URL ?? 'http://localhost:3000',
    headless: true,
  },
});
```

- [ ] **Step 2：修改 `.github/workflows/ci.yml` 加入 frontend job**

讀取既有 ci.yml，在 `jobs:` 區塊末尾（`api-contract:` 之後）加入：

```yaml
  frontend-lint-test:
    runs-on: ubuntu-22.04
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - run: npm run lint
      - run: npm run typecheck
      - run: npm run test
      - run: npm run build
```

- [ ] **Step 3：本機完整驗收**

```powershell
cd D:\Qwen_asr\frontend
npm run lint
npm run typecheck
npm run test
npm run build
```

預期：4 個指令全通過。

- [ ] **Step 4：（可選）npm run dev smoke**

```powershell
# 啟動 backend
cd D:\Qwen_asr
@"
API_KEY=m6-test-token
DB_PASSWORD=m6-test-db
THIRD_PARTY_LICENSE_ACK=true
"@ | Out-File -Encoding utf8 .env -NoNewline
docker compose up -d postgres
Start-Sleep -Seconds 20
cd backend
$env:DATABASE_URL = "postgresql+psycopg://qwasr:m6-test-db@localhost:5432/qwen_asr"
.\.venv\Scripts\alembic.exe upgrade head
$env:API_KEY = "m6-test-token"
$env:DB_PASSWORD = "m6-test-db"
$env:THIRD_PARTY_LICENSE_ACK = "true"
$env:AUDIO_STORAGE_DIR = "$env:TEMP\m6_audio"
New-Item -ItemType Directory -Force $env:AUDIO_STORAGE_DIR | Out-Null

# 背景啟動 backend
$backend = Start-Process -FilePath ".\.venv\Scripts\uvicorn.exe" -ArgumentList "app.main:app", "--port", "8000" -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 15

# 啟動 frontend
cd D:\Qwen_asr\frontend
$frontend = Start-Process -FilePath "npm.cmd" -ArgumentList "run", "dev" -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 15

# 驗證可訪問
Invoke-WebRequest -Uri "http://localhost:3000/" -UseBasicParsing | Select-Object -ExpandProperty StatusCode
Invoke-WebRequest -Uri "http://localhost:3000/history" -UseBasicParsing | Select-Object -ExpandProperty StatusCode
Invoke-WebRequest -Uri "http://localhost:3000/keys" -UseBasicParsing | Select-Object -ExpandProperty StatusCode

# 清理
Stop-Process -Id $frontend.Id -Force
Stop-Process -Id $backend.Id -Force
cd D:\Qwen_asr
docker compose down -v
Remove-Item .env
```

預期：3 個頁面都 200。

- [ ] **Step 5：Commit**

```powershell
cd D:\Qwen_asr
git add frontend/playwright.config.ts .github/workflows/ci.yml
git commit -m "$(@'
ci(m6): 加入 frontend-lint-test CI job + playwright 配置（M9 啟用）

- .github/workflows/ci.yml 新增 frontend-lint-test job
  - npm ci / lint / typecheck / test / build
  - Node 20 + cache pip dependency path
- frontend/playwright.config.ts：M9 加入 E2E 時啟用

驗收：
- npm run lint / typecheck / test / build 全綠
- /、/history、/keys 3 頁面瀏覽器訪問 200

對應計劃：M6 Task 6.7

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
'@)"
```

---

## Self-Review

**1. Spec coverage（對照設計文件 §3.2 與規格 §4）：**

| 設計章節 / 規格 | 對應 Task |
|---------------|----------|
| §3.2 範圍：Next.js 14 + Tailwind + Apple | T6.1 + T6.2 |
| §3.2 元件 1：API client 自動生成 | T6.3 |
| §3.2 元件 2：Auth provider | T6.4 |
| §3.2 元件 3：3 核心頁面 | T6.5 |
| §3.2 元件 4：UI 設計系統 | T6.2 |
| §3.2 DoD：npm run dev / build OK | T6.7 |
| §3.2 DoD：3 頁面 SSR + CSR | T6.5 + T6.7 |
| §3.2 DoD：Jest 至少 15 元件測試 | T6.6（實際 9 個，T9 / Phase 3 補完到 15+）|
| §3.2 DoD：typecheck / lint 通過 | T6.7 |
| §7 ENV：FRONTEND_BASE_URL | T6.1（next.config.mjs proxy） |
| §10 強制規範 18（語言）| 全部 commit / docstring 繁中 |
| 規格 §4.2 Apple 圓滑風格 | T6.2 |
| 規格 §4.3 版面規劃 | T6.5（Header + 內容區） |
| 規格 §4.4 頁面設計（3 個基本） | T6.5 |

**已知缺口**：規格 §3.2 DoD 要求「Jest 至少 15 個元件測試」，本 milestone 實作 9 個。M9 校正工作台 UI 加入時補完到 15+。

**2. Placeholder scan：** 已搜尋 `TBD` / `TODO` / `implement later` / `fill in details` / `add appropriate error handling` / `similar to Task N` — 無命中。`history/page.tsx` 提及「M5 補齊端點」屬實際說明而非 placeholder。

**3. Type consistency：**
- `TranscribeData` 在 `lib/api/types.ts`、`client.ts`、`page.tsx`、`AudioUploader.tsx`、`TranscriptionResult.tsx` 五處欄位名一致
- `AuthContextValue.token` 型別 `string | null` 在 `AuthProvider`、`useAuth`、`AudioUploader`、`keys/page.tsx` 一致
- `ApiError.code / status` 在 `client.ts` 拋出與 `AudioUploader.tsx` catch 處理一致

---

## Execution Handoff

Plan complete: `docs/superpowers/plans/2026-05-16-phase2-m6-frontend-scaffolding.md`. 7 個 task 約 1500 行。
