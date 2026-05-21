'use client';

import { type ReactNode } from 'react';

interface Props {
  audioPanel: ReactNode;
  listPanel: ReactNode;
  editorPanel: ReactNode;
  toolbar?: ReactNode;
}

export function CorrectionLayout({ audioPanel, listPanel, editorPanel, toolbar }: Props) {
  return (
    <div className="correction-page">
      <div className="correction-body">
        <aside className="correction-audio" aria-label="音訊區">{audioPanel}</aside>
        <aside className="correction-list" aria-label="段落清單">{listPanel}</aside>
        <main className="correction-editor" aria-label="文字編輯區">
          {editorPanel}
        </main>
      </div>
      {toolbar && <div role="toolbar">{toolbar}</div>}
    </div>
  );
}
