import pytest
from app.services.finetune.state_machine import (
    can_transition,
    is_active,
    is_terminal,
    is_valid_state,
)


def test_valid_states() -> None:
    for s in ["pending", "preparing", "training", "evaluating", "completed", "failed"]:
        assert is_valid_state(s)
    assert not is_valid_state("unknown")


@pytest.mark.parametrize("from_state,to_state,expected", [
    ("pending", "preparing", True),
    ("pending", "training", False),
    ("preparing", "training", True),
    ("training", "evaluating", True),
    ("evaluating", "completed", True),
    ("evaluating", "failed", True),
    ("completed", "preparing", False),
    ("failed", "training", False),
    ("training", "failed", True),
])
def test_transitions(from_state: str, to_state: str, expected: bool) -> None:
    assert can_transition(from_state, to_state) == expected


def test_is_terminal() -> None:
    assert is_terminal("completed")
    assert is_terminal("failed")
    assert not is_terminal("training")


def test_is_active() -> None:
    assert is_active("pending")
    assert is_active("training")
    assert not is_active("completed")
    assert not is_active("failed")
