import type { TranscribeData } from '@/lib/api/types';
import { Card } from '@/components/ui/Card';

interface Props {
  data: TranscribeData;
  /**
   * 從前端按下「開始辨識」到收到 response 的牆鐘時間，包含檔案上傳、
   * 網路往返、後端排隊、後端 pipeline 處理。與 backend 自報的
   * `processing_duration_sec`（純 ASR pipeline）區隔開。
   */
  clientElapsedMs?: number;
}

export function TranscriptionResult({ data, clientElapsedMs }: Props) {
  return (
    <Card className="mt-4">
      <h2 className="text-lg font-semibold mb-4">辨識結果</h2>
      {data.text ? (
        <p className="whitespace-pre-wrap text-base mb-4">{data.text}</p>
      ) : (
        <p className="text-sm text-foreground/60 italic mb-4">
          辨識結果為空字串（音檔可能無有效語音段，或全為靜音 / 噪音）
        </p>
      )}
      <dl className="grid grid-cols-2 gap-2 text-sm text-foreground/70">
        <dt>音檔長度</dt>
        <dd>{data.duration_sec.toFixed(2)} 秒</dd>
        <dt>ASR 後端純處理</dt>
        <dd>{data.processing_duration_sec.toFixed(2)} 秒</dd>
        {clientElapsedMs !== undefined && (
          <>
            <dt>客戶端總耗時</dt>
            <dd>
              {(clientElapsedMs / 1000).toFixed(2)} 秒
              <span className="text-xs text-foreground/50 ml-1">（含上傳 / 網路 / 排隊）</span>
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
