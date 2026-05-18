"""GPU 整合測試：需真實 GPU 環境執行（pytest -m gpu）。

執行方式（Linux GPU 環境）：
  cd /app
  pytest tests/integration/test_asr_gpu_smoke.py -m gpu -v -s

前提：
  1. INSTALL_GPU_DEPS=true 的 Docker image 已建立
  2. GPU 可見（nvidia-smi 正常）
  3. Qwen3-ASR-1.7B 與 Qwen3-ForcedAligner-0.6B 已下載至 MODEL_CACHE_DIR
  4. 環境變數：API_KEY、DATABASE_URL、DB_PASSWORD、THIRD_PARTY_LICENSE_ACK=true
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest


@pytest.mark.gpu
def test_qwen3_asr_model_imports() -> None:
    """確認 qwen-asr 套件可正確 import，Qwen3ASRModel.LLM 存在。"""
    from qwen_asr import Qwen3ASRModel  # noqa: PLC0415

    assert hasattr(Qwen3ASRModel, "LLM"), "Qwen3ASRModel 缺少 LLM 屬性"


@pytest.mark.gpu
def test_asr_engine_initialize_and_transcribe(tmp_path: Path) -> None:
    """端到端 GPU 測試：初始化引擎 → 以 dummy audio 執行 transcribe → 驗證回傳格式。

    本測試不驗證辨識準確度（語音內容為白雜訊），只驗證介面不拋例外、
    回傳物件含 text / language / time_stamps。
    """
    import numpy as np  # noqa: PLC0415

    from app.core.config import Settings  # noqa: PLC0415
    from app.services.asr.engine import AsrEngineManager  # noqa: PLC0415

    model_cache_dir = Path(os.environ.get("MODEL_CACHE_DIR", "/data/models"))
    settings = Settings(
        API_KEY=os.environ["API_KEY"],
        DATABASE_URL=os.environ["DATABASE_URL"],
        DB_PASSWORD=os.environ["DB_PASSWORD"],
        THIRD_PARTY_LICENSE_ACK=True,
        MODEL_CACHE_DIR=model_cache_dir,
        VLLM_GPU_MEMORY_UTILIZATION=0.8,
        MAX_INFERENCE_BATCH=1,
        ASR_MAX_TOKENS=256,
        FORCED_ALIGNER_MODEL="Qwen/Qwen3-ForcedAligner-0.6B",
        FORCED_ALIGNER_DEVICE="cuda:0",
        FORCED_ALIGNER_DTYPE="bfloat16",
    )  # type: ignore[call-arg]

    # 初始化引擎（真實 GPU 載入）
    AsrEngineManager.initialize(settings)
    try:
        asr: Any = AsrEngineManager.get_asr()

        # 產生 1 秒 16kHz mono 白雜訊作為 dummy input
        dummy_wav = np.zeros(16000, dtype=np.float32)
        sample_rate = 16000

        results = asr.transcribe(
            audio=[(dummy_wav, sample_rate)],
            context=[""],
            language=[None],
            return_time_stamps=True,
        )

        assert len(results) == 1
        result = results[0]
        assert hasattr(result, "text"), "result 缺少 text 屬性"
        assert hasattr(result, "language"), "result 缺少 language 屬性"
        assert hasattr(result, "time_stamps"), "result 缺少 time_stamps 屬性"
        assert isinstance(result.text, str), f"result.text 非字串：{type(result.text)}"

    finally:
        AsrEngineManager.shutdown()


@pytest.mark.gpu
def test_smoke_script_executes() -> None:
    """確認 smoke_asr.sh 腳本語法正確（僅解析，不執行真實 HTTP 請求）。"""
    import subprocess  # noqa: PLC0415

    smoke_script = Path("scripts/smoke_asr.sh")
    assert smoke_script.exists(), f"smoke script 不存在：{smoke_script}"

    result = subprocess.run(
        ["bash", "-n", str(smoke_script)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"smoke script 語法錯誤：{result.stderr}"
