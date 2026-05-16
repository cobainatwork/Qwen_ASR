"""L4 LLM 糾錯（local Qwen2.5-7B INT4 或 OpenAI）。"""

from __future__ import annotations

from typing import Protocol


class _LlmBackend(Protocol):
    async def complete(self, prompt: str) -> str: ...


class LlmCorrector:
    _backend: _LlmBackend | None = None
    _backend_name: str = "none"

    @classmethod
    def set_backend_for_test(cls, backend: _LlmBackend | None, name: str = "test") -> None:
        cls._backend = backend
        cls._backend_name = name

    @classmethod
    def is_ready(cls) -> bool:
        return cls._backend is not None

    @classmethod
    async def correct(cls, text: str, context: str | None = None) -> str:
        if cls._backend is None:
            raise RuntimeError("LLM 糾錯後端未設定")
        prompt = f"請修正以下中文文字的錯字並保持原意，僅回傳修正後的文字：\n{text}"
        if context:
            prompt = f"上下文：{context}\n\n{prompt}"
        return await cls._backend.complete(prompt)
