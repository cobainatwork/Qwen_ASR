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
