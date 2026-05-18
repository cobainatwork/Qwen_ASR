from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.core.exceptions import AsrEngineUnavailableError
from app.services.asr.engine import AsrEngineManager, compute_model_version


# ── compute_model_version（HF cache 優先 → legacy → fallback）──────────────

_REPO_ID = "Qwen/Qwen3-ASR-1.7B"
_SAFE = "Qwen_Qwen3-ASR-1.7B"


def _make_hf_refs_main(cache_dir: Path, repo_id: str, commit_sha: str) -> None:
    refs = cache_dir / f"models--{repo_id.replace('/', '--')}" / "refs"
    refs.mkdir(parents=True, exist_ok=True)
    (refs / "main").write_text(commit_sha)


def test_compute_model_version_from_hf_cache_refs_main(tmp_path: Path) -> None:
    """HF cache layout：取 refs/main commit SHA 前 12 字元。"""
    _make_hf_refs_main(tmp_path, _REPO_ID, "7278e1e70fe206f11671096ffdd38061171dd6e5")
    assert compute_model_version(tmp_path, _REPO_ID) == f"{_SAFE}@7278e1e70fe2"


def test_compute_model_version_hf_cache_priority_over_legacy(tmp_path: Path) -> None:
    """HF cache 與 legacy 同時存在時，優先取 HF cache。"""
    _make_hf_refs_main(tmp_path, _REPO_ID, "abc123def456789abc")
    legacy = tmp_path / _SAFE
    legacy.mkdir()
    (legacy / "version.json").write_text(json.dumps({"version": "legacy"}))
    assert compute_model_version(tmp_path, _REPO_ID) == f"{_SAFE}@abc123def456"


def test_compute_model_version_hf_refs_main_empty_falls_back(tmp_path: Path) -> None:
    """refs/main 存在但內容空字串時 fallback 到 legacy / unknown。"""
    _make_hf_refs_main(tmp_path, _REPO_ID, "")
    assert compute_model_version(tmp_path, _REPO_ID) == f"{_SAFE}@unknown"


def test_compute_model_version_from_version_json(tmp_path: Path) -> None:
    """Legacy local：{cache_dir}/{safe_name}/version.json。"""
    legacy = tmp_path / _SAFE
    legacy.mkdir()
    (legacy / "version.json").write_text(json.dumps({"version": "2026-04-01"}))
    assert compute_model_version(tmp_path, _REPO_ID) == f"{_SAFE}@2026-04-01"


def test_compute_model_version_from_safetensors(tmp_path: Path) -> None:
    """Legacy local：{cache_dir}/{safe_name}/model.safetensors SHA256 前 8 字元。"""
    legacy = tmp_path / _SAFE
    legacy.mkdir()
    (legacy / "model.safetensors").write_bytes(b"fake-weights")
    v = compute_model_version(tmp_path, _REPO_ID)
    assert v.startswith(f"{_SAFE}@")
    assert len(v.split("@")[1]) == 8


def test_compute_model_version_fallback(tmp_path: Path) -> None:
    """任何 source 都不存在時 fallback 為 @unknown。"""
    assert compute_model_version(tmp_path, _REPO_ID) == f"{_SAFE}@unknown"


def test_compute_model_version_invalid_json_fallbacks(tmp_path: Path) -> None:
    """version.json 損壞 + 無 safetensors + 無 HF cache → @unknown。"""
    legacy = tmp_path / _SAFE
    legacy.mkdir()
    (legacy / "version.json").write_text("{ not-valid-json")
    assert compute_model_version(tmp_path, _REPO_ID) == f"{_SAFE}@unknown"


# ── AsrEngineManager 新介面 ──────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_engine() -> Any:
    AsrEngineManager.set_asr_for_test(None, model_version="unknown")
    yield
    AsrEngineManager.set_asr_for_test(None, model_version="unknown")


def test_get_asr_raises_when_not_initialized() -> None:
    with pytest.raises(AsrEngineUnavailableError):
        AsrEngineManager.get_asr()


def test_set_asr_for_test_sets_version() -> None:
    mock_asr: Any = MagicMock()
    AsrEngineManager.set_asr_for_test(mock_asr, model_version="MOCK@1")
    assert AsrEngineManager.model_version() == "MOCK@1"
    assert AsrEngineManager.get_asr() is mock_asr


def test_shutdown_clears_asr() -> None:
    mock_asr: Any = MagicMock()
    AsrEngineManager.set_asr_for_test(mock_asr, model_version="MOCK@1")
    AsrEngineManager.shutdown()
    with pytest.raises(AsrEngineUnavailableError):
        AsrEngineManager.get_asr()


def test_initialize_calls_qwen3_asr_model(tmp_path: Path) -> None:
    """initialize() 必須以正確參數呼叫 Qwen3ASRModel.LLM，不拋例外。"""
    import torch

    from app.core.config import Settings

    settings = Settings(
        API_KEY="test",
        DATABASE_URL="postgresql+psycopg://u:p@h/d",
        DB_PASSWORD="p",
        THIRD_PARTY_LICENSE_ACK=True,
        MODEL_CACHE_DIR=tmp_path,
        ASR_MODEL="Qwen/Qwen3-ASR-1.7B",
        VLLM_GPU_MEMORY_UTILIZATION=0.8,
        MAX_INFERENCE_BATCH=32,
        ASR_MAX_TOKENS=4096,
        FORCED_ALIGNER_MODEL="Qwen/Qwen3-ForcedAligner-0.6B",
        FORCED_ALIGNER_DEVICE="cuda:0",
        FORCED_ALIGNER_DTYPE="bfloat16",
    )  # type: ignore[call-arg]

    mock_asr_instance: Any = MagicMock()
    mock_llm_cls: Any = MagicMock(return_value=mock_asr_instance)

    # Patch 同時 Qwen3ASRModel（可能為 None on CPU CI）與 dtype_map（避免實際 torch import 副作用）
    with patch("app.services.asr.engine.Qwen3ASRModel") as mock_model_cls, \
         patch("app.services.asr.engine._get_dtype_map", return_value={"bfloat16": torch.bfloat16, "float16": torch.float16, "float32": torch.float32}):
        mock_model_cls.LLM = mock_llm_cls
        AsrEngineManager.initialize(settings)

    mock_llm_cls.assert_called_once_with(
        "Qwen/Qwen3-ASR-1.7B",
        gpu_memory_utilization=0.8,
        max_inference_batch_size=32,
        max_new_tokens=4096,
        forced_aligner="Qwen/Qwen3-ForcedAligner-0.6B",
        forced_aligner_kwargs={"dtype": torch.bfloat16, "device_map": "cuda:0"},
        download_dir=str(tmp_path),
    )
    assert AsrEngineManager.get_asr() is mock_asr_instance


def test_initialize_raises_when_qwen_asr_missing(tmp_path: Path) -> None:
    """qwen-asr 套件未安裝時應拋 RuntimeError。"""
    from app.core.config import Settings

    settings = Settings(
        API_KEY="test",
        DATABASE_URL="postgresql+psycopg://u:p@h/d",
        DB_PASSWORD="p",
        THIRD_PARTY_LICENSE_ACK=True,
        MODEL_CACHE_DIR=tmp_path,
    )  # type: ignore[call-arg]

    with patch("app.services.asr.engine.Qwen3ASRModel", None):
        with pytest.raises(RuntimeError, match="qwen-asr 套件未安裝"):
            AsrEngineManager.initialize(settings)


def test_initialize_raises_on_invalid_dtype(tmp_path: Path) -> None:
    """非法 FORCED_ALIGNER_DTYPE 應在進入 Qwen3ASRModel.LLM 之前就拋 RuntimeError。"""
    import torch

    from app.core.config import Settings

    settings = Settings(
        API_KEY="test",
        DATABASE_URL="postgresql+psycopg://u:p@h/d",
        DB_PASSWORD="p",
        THIRD_PARTY_LICENSE_ACK=True,
        MODEL_CACHE_DIR=tmp_path,
        FORCED_ALIGNER_DTYPE="float8",  # type: ignore[arg-type]  # 故意 invalid
    )  # type: ignore[call-arg]

    with patch("app.services.asr.engine.Qwen3ASRModel") as mock_model_cls, \
         patch("app.services.asr.engine._get_dtype_map", return_value={"bfloat16": torch.bfloat16}):
        mock_model_cls.LLM = MagicMock()
        with pytest.raises(RuntimeError, match="FORCED_ALIGNER_DTYPE 不合法"):
            AsrEngineManager.initialize(settings)
