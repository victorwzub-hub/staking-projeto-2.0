from __future__ import annotations

from enum import StrEnum


class ProcessingState(StrEnum):
    CREATED = "created"
    QUEUED = "queued"
    CONNECTING = "connecting"
    EXTRACTING = "extracting"
    RECEIVED = "received"
    VALIDATING = "validating"
    MAPPING = "mapping"
    NORMALIZING = "normalizing"
    LOADING = "loading"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"
    CANCELLED = "cancelled"
    QUARANTINED = "quarantined"
    RETRY_SCHEDULED = "retry_scheduled"


_TRANSITIONS: dict[ProcessingState, frozenset[ProcessingState]] = {
    ProcessingState.CREATED: frozenset(
        {ProcessingState.QUEUED, ProcessingState.CANCELLED, ProcessingState.FAILED}
    ),
    ProcessingState.QUEUED: frozenset(
        {
            ProcessingState.CONNECTING,
            ProcessingState.RECEIVED,
            ProcessingState.CANCELLED,
            ProcessingState.RETRY_SCHEDULED,
            ProcessingState.FAILED,
        }
    ),
    ProcessingState.CONNECTING: frozenset(
        {
            ProcessingState.EXTRACTING,
            ProcessingState.CANCELLED,
            ProcessingState.RETRY_SCHEDULED,
            ProcessingState.FAILED,
        }
    ),
    ProcessingState.EXTRACTING: frozenset(
        {
            ProcessingState.RECEIVED,
            ProcessingState.CANCELLED,
            ProcessingState.RETRY_SCHEDULED,
            ProcessingState.FAILED,
        }
    ),
    ProcessingState.RECEIVED: frozenset(
        {
            ProcessingState.VALIDATING,
            ProcessingState.CANCELLED,
            ProcessingState.RETRY_SCHEDULED,
            ProcessingState.FAILED,
        }
    ),
    ProcessingState.VALIDATING: frozenset(
        {
            ProcessingState.MAPPING,
            ProcessingState.QUARANTINED,
            ProcessingState.CANCELLED,
            ProcessingState.RETRY_SCHEDULED,
            ProcessingState.FAILED,
        }
    ),
    ProcessingState.MAPPING: frozenset(
        {
            ProcessingState.NORMALIZING,
            ProcessingState.QUARANTINED,
            ProcessingState.CANCELLED,
            ProcessingState.RETRY_SCHEDULED,
            ProcessingState.FAILED,
        }
    ),
    ProcessingState.NORMALIZING: frozenset(
        {
            ProcessingState.LOADING,
            ProcessingState.QUARANTINED,
            ProcessingState.CANCELLED,
            ProcessingState.RETRY_SCHEDULED,
            ProcessingState.FAILED,
        }
    ),
    ProcessingState.LOADING: frozenset(
        {
            ProcessingState.COMPLETED,
            ProcessingState.COMPLETED_WITH_WARNINGS,
            ProcessingState.QUARANTINED,
            ProcessingState.CANCELLED,
            ProcessingState.RETRY_SCHEDULED,
            ProcessingState.FAILED,
        }
    ),
    ProcessingState.RETRY_SCHEDULED: frozenset(
        {
            ProcessingState.QUEUED,
            ProcessingState.CONNECTING,
            ProcessingState.RECEIVED,
            ProcessingState.VALIDATING,
            ProcessingState.MAPPING,
            ProcessingState.NORMALIZING,
            ProcessingState.LOADING,
            ProcessingState.CANCELLED,
            ProcessingState.FAILED,
        }
    ),
    ProcessingState.QUARANTINED: frozenset(
        {ProcessingState.QUEUED, ProcessingState.CANCELLED, ProcessingState.FAILED}
    ),
    ProcessingState.COMPLETED: frozenset(),
    ProcessingState.COMPLETED_WITH_WARNINGS: frozenset(),
    ProcessingState.FAILED: frozenset({ProcessingState.QUEUED, ProcessingState.CANCELLED}),
    ProcessingState.CANCELLED: frozenset(),
}

_TERMINAL = frozenset(
    {
        ProcessingState.COMPLETED,
        ProcessingState.COMPLETED_WITH_WARNINGS,
        ProcessingState.CANCELLED,
    }
)


def assert_transition(current: str | ProcessingState, target: str | ProcessingState) -> None:
    source_state = ProcessingState(current)
    target_state = ProcessingState(target)
    if source_state == target_state:
        return
    if target_state not in _TRANSITIONS[source_state]:
        raise ValueError(f"Invalid processing transition: {source_state} -> {target_state}")


def is_terminal_state(state: str | ProcessingState) -> bool:
    return ProcessingState(state) in _TERMINAL


def allowed_transitions(state: str | ProcessingState) -> frozenset[ProcessingState]:
    return _TRANSITIONS[ProcessingState(state)]
