'use client';

interface ConflictDialogProps {
  open: boolean;
  draftText: string;
  draftVersion: number;
  serverText: string;
  serverVersion: number;
  onKeepDraft: () => void;
  onAcceptServer: () => void;
  onLater: () => void;
}

/**
 * 版本衝突對話框（409 CORRECTION_VERSION_MISMATCH）。
 * 提供三種解決動作：採用我的草稿 / 採用最新版本 / 稍後處理。
 */
export function ConflictDialog({
  open,
  draftText,
  draftVersion,
  serverText,
  serverVersion,
  onKeepDraft,
  onAcceptServer,
  onLater,
}: ConflictDialogProps) {
  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="conflict-dialog-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30"
    >
      <div className="w-full max-w-lg space-y-3 rounded-lg bg-white p-4 shadow-lg">
        <h2 id="conflict-dialog-title" className="text-base font-semibold">
          版本衝突
        </h2>
        <p className="text-sm text-gray-600">
          此段落已被他人編輯，您的草稿無法直接套用。請選擇處理方式。
        </p>

        <div className="space-y-1">
          <div className="text-xs text-gray-500">
            您的草稿（version={draftVersion}）：
          </div>
          <div className="rounded bg-amber-50 p-2 text-sm">{draftText}</div>
        </div>

        <div className="space-y-1">
          <div className="text-xs text-gray-500">
            最新後端版本（version={serverVersion}）：
          </div>
          <div className="rounded bg-blue-50 p-2 text-sm">{serverText}</div>
        </div>

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onLater}
            className="rounded border px-3 py-1 text-sm hover:bg-gray-50"
          >
            稍後處理
          </button>
          <button
            type="button"
            onClick={onAcceptServer}
            className="rounded border px-3 py-1 text-sm hover:bg-gray-50"
          >
            採用最新版本
          </button>
          <button
            type="button"
            onClick={onKeepDraft}
            className="rounded bg-blue-500 px-3 py-1 text-sm text-white hover:bg-blue-600"
          >
            採用我的草稿
          </button>
        </div>
      </div>
    </div>
  );
}
