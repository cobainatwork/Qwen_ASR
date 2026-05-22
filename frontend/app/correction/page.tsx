'use client';

import { useState } from 'react';
import Link from 'next/link';

import {
  useCorrectionSessionsListQuery,
  useDeleteCorrectionSessionMutation,
  type CorrectionSession,
} from '@/lib/api/correction';

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString('zh-TW', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    in_progress: 'bg-yellow-500/20 text-yellow-300',
    completed: 'bg-green-500/20 text-green-300',
    pending: 'bg-blue-500/20 text-blue-300',
  };
  const cls = map[status] ?? 'bg-foreground/10 text-foreground/60';
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${cls}`}>
      {status}
    </span>
  );
}

function DeleteButton({ session }: { session: CorrectionSession }) {
  const { mutate, isPending } = useDeleteCorrectionSessionMutation();

  function handleDelete() {
    if (!window.confirm(`確定要刪除工作階段「${session.name}」？此操作不可復原。`)) return;
    mutate(session.id);
  }

  return (
    <button
      onClick={handleDelete}
      disabled={isPending}
      className="ml-3 text-red-400 hover:text-red-300 disabled:opacity-40 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-red-400/50 rounded text-sm"
      aria-label={`刪除工作階段 ${session.name}`}
    >
      {isPending ? '刪除中...' : '刪除'}
    </button>
  );
}

export default function CorrectionIndexPage() {
  const [page, setPage] = useState(1);
  const limit = 20;

  const { data, isLoading, isError } = useCorrectionSessionsListQuery(page, limit);

  if (isLoading) {
    return (
      <main className="p-6">
        <h1 className="text-xl font-semibold mb-4">校正工作台</h1>
        <p className="text-foreground/60">載入中...</p>
      </main>
    );
  }

  if (isError) {
    return (
      <main className="p-6">
        <h1 className="text-xl font-semibold mb-4">校正工作台</h1>
        <p className="text-red-400">載入失敗，請稍後再試。</p>
      </main>
    );
  }

  const items = data?.items ?? [];
  const pagination = data?.pagination;
  const totalPages = pagination?.total_pages ?? 1;

  return (
    <main className="p-6">
      <h1 className="text-xl font-semibold mb-4">校正工作台</h1>

      {items.length === 0 ? (
        <p className="text-foreground/60">目前沒有校正工作階段。</p>
      ) : (
        <>
          <div className="overflow-x-auto rounded-xl border border-foreground/10">
            <table
              role="table"
              className="w-full text-sm"
              aria-label="校正工作階段列表"
            >
              <caption className="sr-only">校正工作階段列表</caption>
              <thead className="bg-foreground/5 text-foreground/60 uppercase text-xs tracking-wide">
                <tr>
                  <th scope="col" className="px-4 py-3 text-left">名稱</th>
                  <th scope="col" className="px-4 py-3 text-left">狀態</th>
                  <th scope="col" className="px-4 py-3 text-left">建立時間</th>
                  <th scope="col" className="px-4 py-3 text-left">更新時間</th>
                  <th scope="col" className="px-4 py-3 text-left">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-foreground/10">
                {items.map((session) => (
                  <tr
                    key={session.id}
                    className="hover:bg-foreground/5 transition-colors"
                  >
                    <td className="px-4 py-3 font-medium">{session.name}</td>
                    <td className="px-4 py-3">
                      <StatusBadge status={session.status} />
                    </td>
                    <td className="px-4 py-3 text-foreground/70">
                      {formatDate(session.created_at)}
                    </td>
                    <td className="px-4 py-3 text-foreground/70">
                      {formatDate(session.updated_at)}
                    </td>
                    <td className="px-4 py-3 flex items-center">
                      <Link
                        href={`/correction/${session.id}`}
                        className="text-accent hover:underline focus:outline-none focus:ring-2 focus:ring-accent/50 rounded"
                      >
                        開啟
                      </Link>
                      <DeleteButton session={session} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="flex items-center gap-3 mt-4 text-sm">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="px-3 py-1.5 rounded-lg border border-foreground/20 disabled:opacity-40 hover:bg-foreground/5 transition-colors"
              >
                上一頁
              </button>
              <span className="text-foreground/60">
                第 {page} 頁，共 {totalPages} 頁（{pagination?.total ?? 0} 筆）
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="px-3 py-1.5 rounded-lg border border-foreground/20 disabled:opacity-40 hover:bg-foreground/5 transition-colors"
              >
                下一頁
              </button>
            </div>
          )}
        </>
      )}
    </main>
  );
}
