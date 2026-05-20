import type { TranscribeData } from '@/lib/api/types';
import { Card } from '@/components/ui/Card';

interface Props {
  data: TranscribeData;
  /**
   * 客戶端按下「開始辨識」到收到 response 的牆鐘時間，毫秒。
   * 此值 ≈ 後端 pipeline 牆鐘（VAD + ASR 推理 + 對齊 + 語者分離 + 後處理）+
   * 上傳/網路/反序列化。**後端目前只記錄 ASR 純推理的 processing_duration_sec**，
   * 沒記其他 pipeline 段 timing，所以從這兩個數字推不出單一段花了多久。
   * 改善需要 backend 為每段加 duration_ms event log（已列為 follow-up）。
   */
  clientElapsedMs?: number;
}

export function TranscriptionResult({ data, clientElapsedMs }: Props) {
  // 給使用者直接看到的差距：客戶端往返 - ASR 純處理 = 其他 pipeline 段 + 網路。
  const otherStagesSec =
    clientElapsedMs !== undefined
      ? Math.max(0, clientElapsedMs / 1000 - data.processing_duration_sec)
      : undefined;

  return (
    <Card>
      <h2 className="text-sm font-semibold mb-2">處理摘要</h2>
      <dl className="grid grid-cols-2 gap-2 text-sm text-foreground/70">
        <dt>音檔長度</dt>
        <dd>{data.duration_sec.toFixed(2)} 秒</dd>
        <dt>ASR 純推理</dt>
        <dd>
          {data.processing_duration_sec.toFixed(2)} 秒
          <span className="text-xs text-foreground/50 ml-1">（僅 ASR 模型）</span>
        </dd>
        {clientElapsedMs !== undefined && (
          <>
            <dt>請求總往返</dt>
            <dd>{(clientElapsedMs / 1000).toFixed(2)} 秒</dd>
            <dt>其他 pipeline + 網路</dt>
            <dd>
              ≈ {otherStagesSec!.toFixed(2)} 秒
              <span className="text-xs text-foreground/50 ml-1">
                （VAD / 對齊 / 語者分離 / 上傳 / 反序列化合計，後端尚未拆分 timing）
              </span>
            </dd>
          </>
        )}
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
