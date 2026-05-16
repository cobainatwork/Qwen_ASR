"""資料增強策略（規格 §15.3）。

可選功能，由 DATA_AUGMENTATION_ENABLED 控制。
- 速度擾動（0.9x / 1.1x）
- 加噪（高斯白噪音）
- SpecAugment（時間 / 頻率 mask）
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AugmentationPlan:
    speed_perturbation: bool
    noise_injection: bool
    spec_augment: bool

    @classmethod
    def from_config(cls, enabled: bool) -> AugmentationPlan:
        if not enabled:
            return cls(speed_perturbation=False, noise_injection=False, spec_augment=False)
        return cls(speed_perturbation=True, noise_injection=True, spec_augment=True)

    def to_runner_args(self) -> list[str]:
        """轉為 finetune_runner.py CLI 參數。"""
        args: list[str] = []
        if self.speed_perturbation:
            args.append("--augment-speed")
        if self.noise_injection:
            args.append("--augment-noise")
        if self.spec_augment:
            args.append("--augment-specaug")
        return args
