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
