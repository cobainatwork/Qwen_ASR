'use client';

export interface CorrectionToolbarProps {
  sessionId: number;
  /** Called when user requests export to dataset */
  onExport?: (datasetId: number) => Promise<void>;
  /** Called when user requests session completion */
  onComplete?: () => Promise<void>;
}

export function CorrectionToolbar(_props: CorrectionToolbarProps) {
  return <div>工具列（待實作）</div>;
}
