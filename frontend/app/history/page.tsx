'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';

import { Card } from '@/components/ui/Card';
import { useQueryClient } from '@tanstack/react-query';
import { useDeleteTranscriptionMutation, useTranscriptionsListQuery } from '@/lib/api/asr';
import { CorrectionApiError, useCreateCorrectionSessionMutation } from '@/lib/api/correction';

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
    completed: 'bg-green-500/20 text-green-300',
    processing: 'bg-yellow-500/20 text-yellow-300',
    failed: 'bg-red-500/20 text-red-300',
  };
  const cls = map[status] ?? 'bg-foreground/10 text-foreground/60';
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${cls}`}>
      {status}
    </span>
  );
}

function DeleteTranscriptionButton({ transcriptionId }: { transcriptionId: number }) {
  const deleteM = useDeleteTranscriptionMutation();

  return (
    <button
      type="button"
      onClick={() => {
        if (
          window.confirm(
            '確定要刪除這筆辨識紀錄？此操作將同時刪除相關的校正工作階段，不可復原。',
          )
        ) {
          deleteM.mutate(transcriptionId);
        }
      }}
      disabled={deleteM.isPending}
      className="rounded-lg border border-red-500/50 bg-red-500/10 px-2 py-1 text-xs text-red-400 hover:bg-red-500/20 disabled:opacity-50 transition-colors"
    >
      {deleteM.isPending ? '刪除中...' : '刪除'}
    </button>
  );
}

function EnterCorrectionButton({ transcriptionId }: { transcriptionId: number }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const createSessionM = useCreateCorrectionSessionMutation();

  const handleClick = async () => {
    try {
      const sess = await createSessionM.mutateAsync({ transcription_id: transcriptionId });
      router.push(`/correction/${sess.id}`);
    } catch (e) {
      if (e instanceof CorrectionApiError && e.code === 'TRANSCRIPTION_NOT_FOUND') {
        window.alert('此辨識紀錄已不存在（可能已被其他 tab 刪除）。列表將重新整理。');
        void queryClient.invalidateQueries({ queryKey: ['asr', 'transcriptions'] });
      } else {
        window.alert(`進入校正失敗：${(e as Error).message}`);
      }
    }
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={createSessionM.isPending}
      className="rounded-lg border border-accent/50 bg-accent/10 px-2 py-1 text-xs text-accent hover:bg-accent/20 disabled:opacity-50 transition-colors"
    >
      {createSessionM.isPending ? '建立中...' : '進入校正'}
    </button>
  );
}

export default function HistoryPage() {
  const [page, setPage] = useState(1);
  const limit = 20;
  const { data, isLoading, isError } = useTranscriptionsListQuery(page, limit);

  if (isLoading) {
    return (
      <div className="h-full overflow-y-auto px-6 py-6">
        <div className="max-w-4xl mx-auto">
          <Card>
            <h2 className="text-lg font-semibold mb-4">歷史紀錄</h2>
            <p className="text-foreground/60 text-sm">載入中...</p>
          </Card>
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="h-full overflow-y-auto px-6 py-6">
        <div className="max-w-4xl mx-auto">
          <Card>
            <h2 className="text-lg font-semibold mb-4">歷史紀錄</h2>
            <p className="text-red-400 text-sm">載入失敗，請稍後再試。</p>
          </Card>
        </div>
      </div>
    );
  }

  const items = data?.items ?? [];
  const pagination = data?.pagination;
  const totalPages = pagination?.total_pages ?? 1;

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="max-w-4xl mx-auto">
        <Card>
          <h2 className="text-lg font-semibold mb-4">歷史紀錄</h2>

          {items.length === 0 ? (
            <p className="text-foreground/60 text-sm">目前沒有歷史辨識紀錄。</p>
          ) : (
            <>
              <div className="overflow-x-auto rounded-xl border border-foreground/10">
                <table
                  role="table"
                  className="w-full text-sm"
                  aria-label="歷史辨識紀錄"
                >
                  <caption className="sr-only">歷史辨識紀錄</caption>
                  <thead className="bg-foreground/5 text-foreground/60 uppercase text-xs tracking-wide">
                    <tr>
                      <th scope="col" className="px-4 py-3 text-left">檔名</th>
                      <th scope="col" className="px-4 py-3 text-left">狀態</th>
                      <th scope="col" className="px-4 py-3 text-left">時長</th>
                      <th scope="col" className="px-4 py-3 text-left">建立時間</th>
                      <th scope="col" className="px-4 py-3 text-left">操作</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-foreground/10">
                    {items.map((tx) => (
                      <tr
                        key={tx.id}
                        className="hover:bg-foreground/5 transition-colors"
                      >
                        <td className="px-4 py-3 font-medium truncate max-w-xs">
                          {tx.file_name ?? `#${tx.id}`}
                        </td>
                        <td className="px-4 py-3">
                          <StatusBadge status={tx.status} />
                        </td>
                        <td className="px-4 py-3 text-foreground/70">
                          {tx.duration_sec != null
                            ? `${tx.duration_sec.toFixed(1)} 秒`
                            : '—'}
                        </td>
                        <td className="px-4 py-3 text-foreground/70">
                          {formatDate(tx.created_at)}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            {tx.status === 'completed' && (
                              <EnterCorrectionButton transcriptionId={tx.id} />
                            )}
                            <DeleteTranscriptionButton transcriptionId={tx.id} />
                          </div>
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
        </Card>
      </div>
    </div>
  );
}
