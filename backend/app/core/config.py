from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Phase 1 環境變數白名單。"""

    model_config = SettingsConfigDict(
        env_file=(".env.local", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ----- 必填 -----
    API_KEY: str
    DATABASE_URL: str
    DB_PASSWORD: str
    THIRD_PARTY_LICENSE_ACK: bool
    ENV: Literal["development", "staging", "production"] = "development"
    DEPLOYMENT_PROFILE: Literal["client", "vendor"] = "client"

    # ----- 模型與 vLLM -----
    ASR_MODEL: str = "Qwen/Qwen3-ASR-1.7B"
    MODEL_CACHE_DIR: Path = Path("/data/models")
    BACKEND_TYPE: Literal["vllm"] = "vllm"
    VLLM_GPU_MEMORY_UTILIZATION: float = 0.5
    GPU_DEVICE: str = "cuda:0"
    MAX_INFERENCE_BATCH: int = 32
    ASR_MAX_TOKENS: int = 4096
    ASR_REQUEST_TIMEOUT_SEC: int = 1200
    ASR_AUDIO_MAX_DURATION_SEC: int = 1200

    # ----- 音檔處理 -----
    AUDIO_STORAGE_DIR: Path = Path("/data/audio")
    VAD_ENABLED: bool = True
    VAD_MODEL_PATH: Path = Path("/data/models/FireRedVAD/model.bin")
    MAX_UPLOAD_SIZE_MB: int = 100
    MAX_DECODE_SIZE_MB: int = 500
    SUPPORTED_AUDIO_FORMATS: str = "wav,mp3,mp4,flac,aac,ogg,m4a"

    # ----- 佇列 -----
    QUEUE_BATCH_MAX_SIZE: int = 20
    QUEUE_REALTIME_MAX_SIZE: int = 50
    QUEUE_REJECT_BEHAVIOR: Literal["reject", "wait"] = "reject"

    # ----- 可觀測性 -----
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    LOG_FORMAT: Literal["json", "text"] = "json"

    # ----- 安全與 CORS -----
    CORS_ORIGINS: str = "http://localhost:3000"
    CORS_ALLOW_CREDENTIALS: bool = False
    OPENAPI_DOCS_ENABLED: bool = True
    OPENAPI_DOCS_REQUIRE_AUTH: bool = False

    # ----- Hotword 三層分流閾值 -----
    HOTWORD_SHALLOW_FUSION_THRESHOLD: int = 100
    HOTWORD_CTC_WS_THRESHOLD: int = 1000

    # ----- Phase 2 / M7 -----
    ALIGNER_ENABLED: bool = True
    ALIGNER_MODEL_PATH: Path = Path("/data/models/Qwen3-ForcedAligner-0.6B")
    ALIGNER_MAX_DURATION_SEC: int = 300  # 5 分鐘

    DIARIZATION_ENABLED: bool = True
    DIARIZATION_BACKEND: Literal["pyannote", "campp"] = "pyannote"

    POST_PROCESSING_ENABLED: bool = True

    CORRECTION_NEC_ENABLED: bool = False
    CORRECTION_KENLM_ENABLED: bool = False
    CORRECTION_KENLM_MODEL_PATH: Path | None = None
    CORRECTION_HOMOPHONE_ENABLED: bool = False
    CORRECTION_LLM_BACKEND: Literal["none", "local", "openai"] = "none"

    HF_TOKEN: str | None = None  # pyannote 載入需要

    FINETUNE_LOCK_PATH: Path = Path("/data/finetune.lock")
    DATA_AUGMENTATION_ENABLED: bool = False
    FINETUNE_GPU_FRACTION: float = 0.65

    # ----- 補充：認證查找用 HMAC 密鑰 -----
    # 注意：Phase 1 暫以 API_KEY 衍生 HMAC 密鑰；正式部署應獨立提供
    LOOKUP_HMAC_KEY: str | None = None

    @field_validator("LOG_FORMAT")
    @classmethod
    def enforce_json_in_phase1(cls, v: str) -> str:
        if v != "json":
            raise ValueError("Phase 1 強制 LOG_FORMAT=json（CLAUDE.md 規範 20）")
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def supported_formats_list(self) -> list[str]:
        return [f.strip().lower() for f in self.SUPPORTED_AUDIO_FORMATS.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
