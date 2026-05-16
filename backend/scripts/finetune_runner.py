"""Fine-tune 訓練子程序入口。

實際訓練邏輯（LoRA / QLoRA + datasets + transformers Trainer）依
Qwen3-ASR-1.7B 官方文件補完。本 milestone 提供結構與 stdout JSONL 通訊
協議，讓主程式可監聽進度並更新 DB。

執行範例：
  python scripts/finetune_runner.py \\
    --task-id 1 \\
    --dataset-id 2 \\
    --base-model Qwen/Qwen3-ASR-1.7B \\
    --config '{"epochs": 3, "lr": 1e-4}' \\
    --gpu-fraction 0.65
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any


def emit(event_type: str, **payload: Any) -> None:
    """以 JSONL 寫到 stdout（主程式監聽）。"""
    line = json.dumps({"event": event_type, **payload}, ensure_ascii=False)
    print(line, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", type=int, required=True)
    parser.add_argument("--dataset-id", type=int, required=True)
    parser.add_argument("--base-model", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--gpu-fraction", type=float, default=0.65)
    parser.add_argument("--augment-speed", action="store_true")
    parser.add_argument("--augment-noise", action="store_true")
    parser.add_argument("--augment-specaug", action="store_true")
    args = parser.parse_args()

    config = json.loads(args.config)
    epochs = int(config.get("epochs", 3))

    emit("start", task_id=args.task_id, base_model=args.base_model)

    # 占位：實際訓練邏輯
    # 1. torch.cuda.set_per_process_memory_fraction(args.gpu_fraction)
    # 2. 載入 dataset（從 DB / 檔案）
    # 3. 套用資料增強（augment_speed / noise / specaug）
    # 4. LoRA / QLoRA 訓練迴圈
    # 5. 每 epoch emit("epoch", epoch=i, loss=...)
    # 6. 評估 + emit("evaluation", wer=...)
    # 7. emit("complete") + return 0

    # 本占位：模擬 3 個 epoch 後成功
    for epoch in range(1, epochs + 1):
        time.sleep(0.1)
        emit("epoch", epoch=epoch, step=100 * epoch, loss=1.0 / epoch, wer=None)

    emit("evaluation", wer=0.15)
    emit("complete", task_id=args.task_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
