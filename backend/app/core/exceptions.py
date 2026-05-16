"""應用例外與錯誤碼字典。錯誤碼對應規格附錄 A。"""

from typing import Any


class AppException(Exception):
    """所有業務例外的基底。"""

    code: str = "INTERNAL_ERROR"
    http_status: int = 500
    message: str = "伺服器內部錯誤"

    def __init__(
        self,
        code: str | None = None,
        message: str | None = None,
        http_status: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if code is not None:
            self.code = code
        if message is not None:
            self.message = message
        if http_status is not None:
            self.http_status = http_status
        self.details = details
        super().__init__(self.message)


# ----- 認證 / 授權 -----
class UnauthorizedError(AppException):
    code = "AUTH_INVALID_TOKEN"
    http_status = 401
    message = "認證失敗"


class MissingBearerError(AppException):
    code = "AUTH_MISSING_BEARER"
    http_status = 401
    message = "缺失 Authorization Bearer 標頭"


class ForbiddenError(AppException):
    code = "AUTH_SCOPE_INSUFFICIENT"
    http_status = 403
    message = "權限不足"


# ----- 資料 -----
class NotFoundError(AppException):
    code = "NOT_FOUND"
    http_status = 404
    message = "資源不存在"


class ValidationFailedError(AppException):
    code = "VALIDATION_ERROR"
    http_status = 422
    message = "請求驗證失敗"


# ----- 音檔處理 -----
class AudioMimeInvalidError(AppException):
    code = "AUDIO_MIME_INVALID"
    http_status = 400
    message = "音檔格式不在白名單"


class AudioFileTooLargeError(AppException):
    code = "AUDIO_FILE_TOO_LARGE"
    http_status = 413
    message = "音檔超過大小上限"


class AudioDecodeTimeoutError(AppException):
    code = "AUDIO_DECODE_TIMEOUT"
    http_status = 504
    message = "音檔解碼超時"


class AudioResampleFailedError(AppException):
    code = "AUDIO_RESAMPLE_FAILED"
    http_status = 500
    message = "重取樣失敗"


class AudioNoSpeechError(AppException):
    code = "AUDIO_NO_SPEECH"
    http_status = 422
    message = "音檔未偵測到語音"


class AudioVadNotReadyError(AppException):
    code = "AUDIO_VAD_NOT_READY"
    http_status = 503
    message = "VAD 模組尚未就緒"


class AudioVadFailedError(AppException):
    code = "AUDIO_VAD_FAILED"
    http_status = 500
    message = "VAD 推理失敗"


class AudioStorageFailedError(AppException):
    code = "AUDIO_STORAGE_FAILED"
    http_status = 500
    message = "音檔儲存失敗"


# ----- ASR -----
class AsrEngineUnavailableError(AppException):
    code = "ASR_ENGINE_UNAVAILABLE"
    http_status = 503
    message = "ASR 推理引擎未就緒"


class AsrAudioTooLongError(AppException):
    code = "ASR_AUDIO_TOO_LONG"
    http_status = 413
    message = "音檔長度超過 20 分鐘上限"


class AsrCudaError(AppException):
    code = "ASR_CUDA_ERROR"
    http_status = 503
    message = "GPU 推理錯誤"


class AsrInferenceFailedError(AppException):
    code = "ASR_INFERENCE_FAILED"
    http_status = 500
    message = "ASR 推理失敗"


class AsrRequestTimeoutError(AppException):
    code = "ASR_REQUEST_TIMEOUT"
    http_status = 504
    message = "ASR 請求等待逾時"


class QueueFullError(AppException):
    code = "QUEUE_FULL"
    http_status = 503
    message = "處理佇列已滿"


# ----- Phase 2 / M5 -----
class HotwordGroupNotFoundError(AppException):
    code = "HOTWORD_GROUP_NOT_FOUND"
    http_status = 404
    message = "Hotword 群組不存在"


class HotwordTooLargeError(AppException):
    code = "HOTWORD_TOO_LARGE"
    http_status = 422
    message = "Hotword 群組超過 1000 詞，請建立 Fine-tune 任務"


class DatasetNotFoundError(AppException):
    code = "DATASET_NOT_FOUND"
    http_status = 404
    message = "Dataset 不存在"


class DatasetSampleInvalidError(AppException):
    code = "DATASET_SAMPLE_INVALID"
    http_status = 400
    message = "樣本資料不符規範"


# ----- Phase 2 / M7 -----
class AlignerNotReadyError(AppException):
    code = "ALIGNER_NOT_READY"
    http_status = 503
    message = "ForcedAligner 模組尚未就緒"


class AlignerAudioTooLongError(AppException):
    code = "ALIGNER_AUDIO_TOO_LONG"
    http_status = 413
    message = "音檔長度超過 ForcedAligner 5 分鐘上限"


class AlignerFailedError(AppException):
    code = "ALIGNER_FAILED"
    http_status = 500
    message = "對齊失敗（已寫入 post_processing.aligner_failed）"


class DiarizationFailedError(AppException):
    code = "DIARIZATION_FAILED"
    http_status = 500
    message = "語者分離失敗"


class DiarizationNotReadyError(AppException):
    code = "DIARIZATION_NOT_READY"
    http_status = 503
    message = "語者分離模組尚未就緒"


class CorrectionLlmUnavailableError(AppException):
    code = "CORRECTION_LLM_UNAVAILABLE"
    http_status = 503
    message = "LLM 糾錯模型未載入"


# 完整錯誤碼清單（用於 OpenAPI 文件與測試自動化）
ALL_ERROR_CODES: tuple[str, ...] = (
    "INTERNAL_ERROR",
    "AUTH_INVALID_TOKEN",
    "AUTH_MISSING_BEARER",
    "AUTH_SCOPE_INSUFFICIENT",
    "NOT_FOUND",
    "VALIDATION_ERROR",
    "AUDIO_MIME_INVALID",
    "AUDIO_FILE_TOO_LARGE",
    "AUDIO_DECODE_TIMEOUT",
    "AUDIO_RESAMPLE_FAILED",
    "AUDIO_NO_SPEECH",
    "AUDIO_VAD_NOT_READY",
    "AUDIO_VAD_FAILED",
    "AUDIO_STORAGE_FAILED",
    "ASR_ENGINE_UNAVAILABLE",
    "ASR_AUDIO_TOO_LONG",
    "ASR_CUDA_ERROR",
    "ASR_INFERENCE_FAILED",
    "ASR_REQUEST_TIMEOUT",
    "QUEUE_FULL",
    "HOTWORD_GROUP_NOT_FOUND",
    "HOTWORD_TOO_LARGE",
    "DATASET_NOT_FOUND",
    "DATASET_SAMPLE_INVALID",
    "ALIGNER_NOT_READY",
    "ALIGNER_AUDIO_TOO_LONG",
    "ALIGNER_FAILED",
    "DIARIZATION_FAILED",
    "DIARIZATION_NOT_READY",
    "CORRECTION_LLM_UNAVAILABLE",
)
