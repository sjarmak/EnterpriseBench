"""Event and action type definitions and validation for event-replay tasks.

Defines the schema for events.jsonl and actions.jsonl, plus validation logic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------

class EventCategory(str, Enum):
    CICD = "cicd"
    MONITORING = "monitoring"
    COLLABORATION = "collaboration"
    INFRASTRUCTURE = "infrastructure"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    FATAL = "fatal"


# Known event types per category.  The schema is open (payload is free-form),
# but we enumerate common types for documentation / validation hints.
KNOWN_EVENT_TYPES: dict[str, list[str]] = {
    "cicd": [
        "build_failure", "test_failure", "deploy_started",
        "deploy_completed", "deploy_failed", "pipeline_timeout",
    ],
    "monitoring": [
        "error_rate_spike", "latency_p99_increase", "oom_kill",
        "cpu_saturation", "memory_pressure", "disk_full",
        "health_check_failure",
    ],
    "collaboration": [
        "pr_comment", "issue_filed", "slack_message",
        "pagerduty_alert", "review_requested",
    ],
    "infrastructure": [
        "node_unhealthy", "certificate_expiring", "dns_failure",
        "network_partition", "autoscaler_event",
    ],
}

ALL_KNOWN_EVENT_TYPES = {t for types in KNOWN_EVENT_TYPES.values() for t in types}


@dataclass
class Event:
    """A single event in the event stream.

    Fields:
        timestamp_ms: Milliseconds since scenario start (T=0).
        event_type:   One of the known event types (extensible).
        category:     cicd | monitoring | collaboration | infrastructure.
        source:       Logical source (e.g. "github-actions", "datadog", "slack").
        severity:     info | warning | critical | fatal.
        summary:      Short human-readable description.
        payload:      Arbitrary dict with type-specific details.
        id:           Optional unique event identifier.
    """
    timestamp_ms: int
    event_type: str
    category: str
    source: str
    severity: str
    summary: str
    payload: dict[str, Any] = field(default_factory=dict)
    id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if d["id"] is None:
            del d["id"]
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Event":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def validate(self) -> list[str]:
        """Return list of validation errors (empty = valid)."""
        errors: list[str] = []
        if self.timestamp_ms < 0:
            errors.append(f"timestamp_ms must be >= 0, got {self.timestamp_ms}")
        if self.category not in [e.value for e in EventCategory]:
            errors.append(f"unknown category: {self.category}")
        if self.severity not in [e.value for e in Severity]:
            errors.append(f"unknown severity: {self.severity}")
        if self.event_type not in ALL_KNOWN_EVENT_TYPES:
            errors.append(f"unknown event_type: {self.event_type} (not fatal, schema is extensible)")
        return errors


# ---------------------------------------------------------------------------
# Action types
# ---------------------------------------------------------------------------

class ActionType(str, Enum):
    INVESTIGATE = "investigate"      # Look into a specific component/log/metric
    ESCALATE = "escalate"            # Page someone / raise priority
    REMEDIATE = "remediate"          # Apply a fix (code change, config change)
    COMMUNICATE = "communicate"      # Post status update / notify stakeholders
    DEPLOY = "deploy"                # Trigger a deployment
    ROLLBACK = "rollback"            # Revert a deployment
    TRIAGE = "triage"                # Categorize / prioritize an issue
    MONITOR = "monitor"              # Set up or adjust monitoring/alerting
    NO_OP = "no_op"                  # Explicitly decide no action needed


@dataclass
class Action:
    """An action produced by the agent (or the oracle).

    Fields:
        timestamp_ms:    When the agent decided to take this action.
        action_type:     One of the ActionType values.
        target:          What the action targets (service name, PR, deployment, etc.).
        description:     Free-text description of what the agent does.
        triggered_by:    Optional event id(s) that prompted this action.
        payload:         Arbitrary dict with action-specific details.
        id:              Optional unique action identifier.
    """
    timestamp_ms: int
    action_type: str
    target: str
    description: str
    triggered_by: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)
    id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if d["id"] is None:
            del d["id"]
        if not d["triggered_by"]:
            del d["triggered_by"]
        if not d["payload"]:
            del d["payload"]
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Action":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.timestamp_ms < 0:
            errors.append(f"timestamp_ms must be >= 0, got {self.timestamp_ms}")
        valid_types = [e.value for e in ActionType]
        if self.action_type not in valid_types:
            errors.append(f"unknown action_type: {self.action_type}")
        if not self.target:
            errors.append("target must be non-empty")
        return errors


# ---------------------------------------------------------------------------
# File I/O helpers
# ---------------------------------------------------------------------------

def load_events(path: str | Path) -> list[Event]:
    """Load events from a .jsonl file."""
    events = []
    with open(path) as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                events.append(Event.from_dict(d))
            except (json.JSONDecodeError, TypeError) as e:
                raise ValueError(f"Invalid JSON on line {i} of {path}: {e}")
    return events


def load_actions(path: str | Path) -> list[Action]:
    """Load actions from a .jsonl file."""
    actions = []
    with open(path) as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                actions.append(Action.from_dict(d))
            except (json.JSONDecodeError, TypeError) as e:
                raise ValueError(f"Invalid JSON on line {i} of {path}: {e}")
    return actions


def validate_event_file(path: str | Path) -> list[str]:
    """Validate an events.jsonl file. Returns list of errors."""
    errors: list[str] = []
    try:
        events = load_events(path)
    except ValueError as e:
        return [str(e)]

    if not events:
        errors.append("events.jsonl is empty")
        return errors

    # Check monotonically non-decreasing timestamps
    for i in range(1, len(events)):
        if events[i].timestamp_ms < events[i - 1].timestamp_ms:
            errors.append(
                f"Event {i+1} timestamp ({events[i].timestamp_ms}) < "
                f"event {i} timestamp ({events[i-1].timestamp_ms})"
            )

    # Per-event validation
    for i, ev in enumerate(events, 1):
        for err in ev.validate():
            errors.append(f"Event {i}: {err}")

    return errors


def validate_action_file(path: str | Path) -> list[str]:
    """Validate an actions.jsonl file. Returns list of errors."""
    errors: list[str] = []
    try:
        actions = load_actions(path)
    except ValueError as e:
        return [str(e)]

    for i, act in enumerate(actions, 1):
        for err in act.validate():
            errors.append(f"Action {i}: {err}")

    return errors


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python event_schema.py [events|actions] <file.jsonl>")
        sys.exit(1)

    kind, path = sys.argv[1], sys.argv[2]
    if kind == "events":
        errs = validate_event_file(path)
    elif kind == "actions":
        errs = validate_action_file(path)
    else:
        print(f"Unknown kind: {kind}")
        sys.exit(1)

    if errs:
        print(f"Validation errors in {path}:")
        for e in errs:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print(f"{path}: OK")
