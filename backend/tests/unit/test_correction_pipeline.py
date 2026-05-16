import pytest
from app.services.correction.homophone import HomophoneCorrector
from app.services.correction.kenlm_corrector import KenlmCorrector
from app.services.correction.llm import LlmCorrector
from app.services.correction.nec import NecCorrector
from app.services.correction.pipeline import CorrectionOptions, run_correction_pipeline


class _FakeNec:
    def correct(self, text: str) -> str:
        return text.replace("錯字", "正字")


class _FakeKenlm:
    def correct(self, text: str) -> str:
        return text + " [kenlm]"


class _FakeLlmBackend:
    async def complete(self, prompt: str) -> str:
        return "llm-fixed"


@pytest.fixture(autouse=True)
def _reset() -> None:
    NecCorrector.set_model_for_test(None)
    KenlmCorrector.set_model_for_test(None)
    HomophoneCorrector.configure(False)
    LlmCorrector.set_backend_for_test(None)
    yield
    NecCorrector.set_model_for_test(None)
    KenlmCorrector.set_model_for_test(None)
    HomophoneCorrector.configure(False)
    LlmCorrector.set_backend_for_test(None)


@pytest.mark.asyncio
async def test_all_layers_skip_when_not_ready() -> None:
    result = await run_correction_pipeline("test", CorrectionOptions(
        nec_enabled=True, kenlm_enabled=True, homophone_enabled=True, llm_enabled=True
    ))
    assert result.final_text == "test"
    assert result.stages == []


@pytest.mark.asyncio
async def test_nec_layer_runs() -> None:
    NecCorrector.set_model_for_test(_FakeNec())
    result = await run_correction_pipeline("含錯字的句子", CorrectionOptions(nec_enabled=True))
    assert result.final_text == "含正字的句子"
    assert result.stages == [{"layer": "nec", "status": "ok"}]


@pytest.mark.asyncio
async def test_layers_chain() -> None:
    NecCorrector.set_model_for_test(_FakeNec())
    KenlmCorrector.set_model_for_test(_FakeKenlm())
    result = await run_correction_pipeline(
        "錯字",
        CorrectionOptions(nec_enabled=True, kenlm_enabled=True),
    )
    assert result.final_text == "正字 [kenlm]"
    assert [s["layer"] for s in result.stages] == ["nec", "kenlm"]


@pytest.mark.asyncio
async def test_layer_failure_does_not_block_next() -> None:
    class _BrokenNec:
        def correct(self, text: str) -> str:
            raise RuntimeError("nec broken")

    NecCorrector.set_model_for_test(_BrokenNec())
    KenlmCorrector.set_model_for_test(_FakeKenlm())
    result = await run_correction_pipeline(
        "input",
        CorrectionOptions(nec_enabled=True, kenlm_enabled=True),
    )
    assert "[kenlm]" in result.final_text
    assert result.stages[0]["status"] == "failed"
    assert result.stages[1]["status"] == "ok"


@pytest.mark.asyncio
async def test_homophone_layer() -> None:
    HomophoneCorrector.configure(True, custom_map={"在": "再"})
    result = await run_correction_pipeline(
        "我在試一次",
        CorrectionOptions(homophone_enabled=True),
    )
    assert result.final_text == "我再試一次"


@pytest.mark.asyncio
async def test_llm_layer() -> None:
    LlmCorrector.set_backend_for_test(_FakeLlmBackend())
    result = await run_correction_pipeline(
        "原文",
        CorrectionOptions(llm_enabled=True),
    )
    assert result.final_text == "llm-fixed"
