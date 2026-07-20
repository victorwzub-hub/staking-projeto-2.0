"""Integration domain primitives."""

from pharma_api.domain.integrations.state_machine import (
    ProcessingState,
    assert_transition,
    is_terminal_state,
)

__all__ = ["ProcessingState", "assert_transition", "is_terminal_state"]
