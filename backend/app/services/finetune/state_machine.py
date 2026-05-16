"""Fine-tune 任務狀態機。

合法轉換：
- pending → preparing
- preparing → training
- training → evaluating
- evaluating → completed
- 任何狀態（除 completed）→ failed
"""

from __future__ import annotations

# 合法狀態
_STATES = frozenset({"pending", "preparing", "training", "evaluating", "completed", "failed"})

# 合法轉換 map（from → set of to）
_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"preparing", "failed"}),
    "preparing": frozenset({"training", "failed"}),
    "training": frozenset({"evaluating", "failed"}),
    "evaluating": frozenset({"completed", "failed"}),
    "completed": frozenset(),
    "failed": frozenset(),
}

_TERMINAL = frozenset({"completed", "failed"})


def is_valid_state(state: str) -> bool:
    return state in _STATES


def can_transition(from_state: str, to_state: str) -> bool:
    if from_state not in _TRANSITIONS:
        return False
    return to_state in _TRANSITIONS[from_state]


def is_terminal(state: str) -> bool:
    return state in _TERMINAL


def is_active(state: str) -> bool:
    """非終態 = active（佔用 FINETUNE_MAX_CONCURRENT 名額）。"""
    return state not in _TERMINAL


class InvalidStateTransitionError(Exception):
    """非業務例外，由 service 層轉換為 AppException。"""
