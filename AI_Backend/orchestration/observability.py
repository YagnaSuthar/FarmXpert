"""
Structured orchestration logging
=================================
One request id on every line, one execution id per agent attempt, so a
production incident can be reconstructed from the logs alone.

What is deliberately NOT logged: agent payloads, farmer personal data, exact
coordinates, and anything resembling a credential. Shapes, codes and durations
tell you what went wrong; the farmer's field data does not belong in a log
aggregator.
"""

from __future__ import annotations

import json
import logging
from enum import Enum
from typing import Any, Dict

logger = logging.getLogger("farmxpert.orchestration")


class Event(str, Enum):
    ORCHESTRATION_STARTED          = "ORCHESTRATION_STARTED"
    ORCHESTRATION_VALIDATION_FAILED = "ORCHESTRATION_VALIDATION_FAILED"
    AGENT_SELECTED                 = "AGENT_SELECTED"
    AGENT_STARTED                  = "AGENT_STARTED"
    AGENT_RETRY                    = "AGENT_RETRY"
    AGENT_COMPLETED                = "AGENT_COMPLETED"
    AGENT_FAILED                   = "AGENT_FAILED"
    AGENT_TIMEOUT                  = "AGENT_TIMEOUT"
    AGENT_SKIPPED                  = "AGENT_SKIPPED"
    DEPENDENCY_FAILED              = "DEPENDENCY_FAILED"
    AGENT_OUTPUT_INVALID           = "AGENT_OUTPUT_INVALID"
    AGENT_CONFLICT_DETECTED        = "AGENT_CONFLICT_DETECTED"
    ORCHESTRATION_COMPLETED        = "ORCHESTRATION_COMPLETED"
    ORCHESTRATION_PARTIAL_SUCCESS  = "ORCHESTRATION_PARTIAL_SUCCESS"
    ORCHESTRATION_FAILED           = "ORCHESTRATION_FAILED"


# Keys that must never be written to a log, whatever a caller nests them in.
_FORBIDDEN = ("key", "token", "secret", "password", "authorization", "credential",
              "dsn", "connection_string", "phone", "email", "aadhaar")

_LEVEL_FOR = {
    Event.ORCHESTRATION_VALIDATION_FAILED: logging.WARNING,
    Event.AGENT_RETRY:            logging.WARNING,
    Event.AGENT_FAILED:           logging.ERROR,
    Event.AGENT_TIMEOUT:          logging.WARNING,
    Event.AGENT_SKIPPED:          logging.INFO,
    Event.DEPENDENCY_FAILED:      logging.WARNING,
    Event.AGENT_OUTPUT_INVALID:   logging.ERROR,
    Event.AGENT_CONFLICT_DETECTED: logging.WARNING,
    Event.ORCHESTRATION_FAILED:   logging.ERROR,
    Event.ORCHESTRATION_PARTIAL_SUCCESS: logging.WARNING,
}


def emit(event: Event, request_id: str, **fields: Any) -> None:
    """Write one structured orchestration event."""
    record: Dict[str, Any] = {"event": event.value, "request_id": request_id}
    for key, value in fields.items():
        if value is None:
            continue
        if _is_sensitive(key):
            continue
        record[key] = _safe(value)
    logger.log(_LEVEL_FOR.get(event, logging.INFO), "%s", _render(record))


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(bad in lowered for bad in _FORBIDDEN)


def _safe(value: Any) -> Any:
    """Keep the log small and free of payloads."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple, set)):
        return [_safe(v) for v in list(value)[:12]]
    if isinstance(value, dict):
        return {k: _safe(v) for k, v in list(value.items())[:12]
                if not _is_sensitive(k)}
    return type(value).__name__


def _render(record: Dict[str, Any]) -> str:
    try:
        return json.dumps(record, default=str, separators=(",", "="))
    except (TypeError, ValueError):
        return str(record)


def log_exception(request_id: str, agent: str, exc: BaseException) -> None:
    """Full detail to the log, never to the client.

    The traceback stays here with the request id, so support can find it from
    the id the farmer's app showed, while the response carries only a code.
    """
    logger.error("Agent raised | request_id=%s agent=%s error=%s: %s",
                 request_id, agent, type(exc).__name__, exc, exc_info=True)


def safe_message(code: "Any", agent: str) -> str:
    """A sentence for the client that reveals nothing about internals."""
    from AI_Backend.orchestration.contracts import ErrorCode
    messages = {
        ErrorCode.TIMEOUT:           f"The {agent} service took too long to answer.",
        ErrorCode.EXTERNAL_SERVICE:  f"An external service used by {agent} is unavailable.",
        ErrorCode.RATE_LIMITED:      f"The {agent} service is rate limited right now.",
        ErrorCode.DATABASE:          f"Stored data needed by {agent} could not be read.",
        ErrorCode.MODEL_UNAVAILABLE: f"The model behind {agent} is not available.",
        ErrorCode.INVALID_OUTPUT:    f"{agent} returned a result that failed validation.",
        ErrorCode.MISSING_INPUT:     f"{agent} needs information that was not provided.",
        ErrorCode.DEPENDENCY_FAILED: f"{agent} could not run because it depends on another agent that failed.",
        ErrorCode.VALIDATION_FAILED: "The request could not be validated.",
        ErrorCode.CANCELLED:         f"{agent} was cancelled.",
    }
    return messages.get(code, f"{agent} could not complete.")

