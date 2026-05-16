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
