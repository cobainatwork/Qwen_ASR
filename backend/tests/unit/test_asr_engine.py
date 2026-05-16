import json
from pathlib import Path

import pytest
from app.core.exceptions import AsrEngineUnavailableError
from app.services.asr.engine import AsrEngineManager, compute_model_version


def test_compute_model_version_from_version_json(tmp_path: Path) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "version.json").write_text(json.dumps({"version": "2026-04-01"}))
    assert compute_model_version(model_dir) == "model@2026-04-01"


def test_compute_model_version_from_safetensors(tmp_path: Path) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "model.safetensors").write_bytes(b"fake-weights")
    v = compute_model_version(model_dir)
    assert v.startswith("model@")
    assert len(v.split("@")[1]) == 8


def test_compute_model_version_fallback(tmp_path: Path) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    assert compute_model_version(model_dir) == "model@unknown"


def test_compute_model_version_invalid_json_fallbacks(tmp_path: Path) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "version.json").write_text("{ not-valid-json")
    assert compute_model_version(model_dir) == "model@unknown"


@pytest.fixture(autouse=True)
def _reset_engine() -> None:
    AsrEngineManager.set_engine_for_test(None, model_version="unknown")
    yield
    AsrEngineManager.set_engine_for_test(None, model_version="unknown")


def test_get_engine_raises_when_not_initialized() -> None:
    with pytest.raises(AsrEngineUnavailableError):
        AsrEngineManager.get_engine()


class _MockEngine:
    async def generate(self, **kwargs):  # type: ignore[no-untyped-def]
        return {"text": "fake"}

    async def abort_all(self) -> None:
        return None


@pytest.mark.asyncio
async def test_set_engine_for_test_and_shutdown() -> None:
    AsrEngineManager.set_engine_for_test(_MockEngine(), model_version="MOCK@1")
    assert AsrEngineManager.model_version() == "MOCK@1"
    assert AsrEngineManager.get_engine() is not None
    await AsrEngineManager.shutdown()
    with pytest.raises(AsrEngineUnavailableError):
        AsrEngineManager.get_engine()
