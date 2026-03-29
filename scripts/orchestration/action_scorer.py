"""Action scorer for event-replay tasks.

Scores agent-produced actions against oracle (ground truth) actions on four
dimensions:
  1. Correctness  - Did the agent take the right actions?
  2. Completeness - Did the agent take ALL needed actions?
  3. Timeliness   - How quickly after the triggering event?
  4. Ordering     - Were dependencies between actions respected?

Usage:
    python action_scorer.py events.jsonl oracle_actions.jsonl agent_actions.jsonl

Output: JSON with per-action and aggregate scores.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

try:
    from .event_schema import Action, Event, load_actions, load_events
except ImportError:
    from event_schema import Action, Event, load_actions, load_events


# ---------------------------------------------------------------------------
# Scoring configuration (tunable per-task via config, sensible defaults here)
# ---------------------------------------------------------------------------

@dataclass
class ScoringConfig:
    # Weights for combining sub-scores into a total (must sum to 1.0)
    weight_correctness: float = 0.35
    weight_completeness: float = 0.30
    weight_timeliness: float = 0.25
    weight_ordering: float = 0.10

    # Timeliness: max acceptable delay (ms) after the triggering event.
    # Actions within this window get full timeliness credit.
    # Actions beyond this get linearly decaying credit down to 0 at 2x.
    timeliness_full_credit_ms: int = 60_000      # 1 minute
    timeliness_zero_credit_ms: int = 300_000      # 5 minutes

    # How to match agent actions to oracle actions
    # "type_and_target" = action_type + target must match
    # "type_only" = just action_type must match (looser)
    match_strategy: str = "type_and_target"


# ---------------------------------------------------------------------------
# Matching: pair agent actions to oracle actions
# ---------------------------------------------------------------------------

@dataclass
class ActionMatch:
    oracle_action: Action
    agent_action: Action | None  # None = oracle action not matched (missed)
    correctness: float = 0.0
    timeliness: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "oracle": self.oracle_action.to_dict(),
            "agent": self.agent_action.to_dict() if self.agent_action else None,
            "correctness": round(self.correctness, 3),
            "timeliness": round(self.timeliness, 3),
        }


def _actions_match(oracle: Action, agent: Action, strategy: str) -> bool:
    """Check if an agent action matches an oracle action."""
    if strategy == "type_and_target":
        return (oracle.action_type == agent.action_type
                and oracle.target.lower() == agent.target.lower())
    elif strategy == "type_only":
        return oracle.action_type == agent.action_type
    else:
        raise ValueError(f"Unknown match strategy: {strategy}")


def match_actions(
    oracle_actions: list[Action],
    agent_actions: list[Action],
    config: ScoringConfig,
) -> list[ActionMatch]:
    """Greedily match agent actions to oracle actions.

    Each oracle action matches at most one agent action (first match wins,
    scanning agent actions in timestamp order).  This is intentionally simple;
    a production scorer might use Hungarian matching for optimality.
    """
    used_agent: set[int] = set()
    matches: list[ActionMatch] = []

    for oracle in oracle_actions:
        best_agent: Action | None = None
        best_idx: int = -1
        for i, agent in enumerate(agent_actions):
            if i in used_agent:
                continue
            if _actions_match(oracle, agent, config.match_strategy):
                best_agent = agent
                best_idx = i
                break  # first match in timestamp order

        match = ActionMatch(oracle_action=oracle, agent_action=best_agent)

        if best_agent is not None:
            used_agent.add(best_idx)
            match.correctness = 1.0
        else:
            match.correctness = 0.0

        matches.append(match)

    return matches


# ---------------------------------------------------------------------------
# Timeliness scoring
# ---------------------------------------------------------------------------

def _build_event_index(events: list[Event]) -> dict[str, Event]:
    """Map event id -> Event for quick lookup."""
    idx: dict[str, Event] = {}
    for ev in events:
        if ev.id:
            idx[ev.id] = ev
    return idx


def score_timeliness(
    match: ActionMatch,
    events: list[Event],
    event_index: dict[str, Event],
    config: ScoringConfig,
) -> float:
    """Score how timely the agent action was relative to its triggering event.

    If no triggering event is identifiable, timeliness defaults to 1.0
    (benefit of the doubt — correctness already penalizes wrong actions).
    """
    if match.agent_action is None:
        return 0.0  # missed action = no timeliness credit

    oracle = match.oracle_action
    agent = match.agent_action

    # Find the triggering event timestamp.
    # Strategy: use the oracle's triggered_by references, falling back to
    # the oracle's own timestamp as an upper-bound proxy.
    trigger_ts: int | None = None

    if oracle.triggered_by:
        # Use the latest triggering event timestamp
        for eid in oracle.triggered_by:
            ev = event_index.get(eid)
            if ev:
                if trigger_ts is None or ev.timestamp_ms > trigger_ts:
                    trigger_ts = ev.timestamp_ms

    if trigger_ts is None:
        # Fallback: use the oracle action's own timestamp as the "ideal" time
        trigger_ts = oracle.timestamp_ms

    delay = agent.timestamp_ms - trigger_ts

    if delay <= 0:
        # Agent acted before or exactly at trigger — full credit
        return 1.0
    elif delay <= config.timeliness_full_credit_ms:
        return 1.0
    elif delay >= config.timeliness_zero_credit_ms:
        return 0.0
    else:
        # Linear decay between full and zero
        window = config.timeliness_zero_credit_ms - config.timeliness_full_credit_ms
        return 1.0 - (delay - config.timeliness_full_credit_ms) / window


# ---------------------------------------------------------------------------
# Ordering scoring
# ---------------------------------------------------------------------------

def score_ordering(
    matches: list[ActionMatch],
    oracle_actions: list[Action],
) -> float:
    """Score whether agent actions preserve the oracle's ordering.

    Uses Kendall tau-style: fraction of oracle-ordered pairs that are also
    correctly ordered in the agent's actions.  Missed actions are ignored
    (completeness already penalizes those).
    """
    # Get the agent timestamps for matched oracle actions, in oracle order
    agent_timestamps: list[int | None] = []
    for m in matches:
        if m.agent_action is not None:
            agent_timestamps.append(m.agent_action.timestamp_ms)
        else:
            agent_timestamps.append(None)

    # Filter to only matched pairs
    matched_ts = [t for t in agent_timestamps if t is not None]

    if len(matched_ts) < 2:
        return 1.0  # trivially ordered

    # Count concordant pairs
    concordant = 0
    total = 0
    for i in range(len(matched_ts)):
        for j in range(i + 1, len(matched_ts)):
            total += 1
            if matched_ts[i] <= matched_ts[j]:
                concordant += 1

    return concordant / total if total > 0 else 1.0


# ---------------------------------------------------------------------------
# Aggregate scoring
# ---------------------------------------------------------------------------

@dataclass
class ScoreResult:
    correctness: float = 0.0
    completeness: float = 0.0
    timeliness: float = 0.0
    ordering: float = 0.0
    total: float = 0.0
    matches: list[dict[str, Any]] = field(default_factory=list)
    extra_actions: int = 0  # agent actions that didn't match any oracle action
    config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def score(
    events: list[Event],
    oracle_actions: list[Action],
    agent_actions: list[Action],
    config: ScoringConfig | None = None,
) -> ScoreResult:
    """Full scoring pipeline."""
    if config is None:
        config = ScoringConfig()

    event_index = _build_event_index(events)

    # 1. Match agent actions to oracle actions
    matches = match_actions(oracle_actions, agent_actions, config)

    # 2. Score timeliness per match
    for m in matches:
        m.timeliness = score_timeliness(m, events, event_index, config)

    # 3. Aggregate correctness = fraction of oracle actions matched
    n_oracle = len(oracle_actions)
    correctness = sum(m.correctness for m in matches) / n_oracle if n_oracle else 1.0

    # 4. Completeness = same as correctness in this greedy scheme
    #    (but conceptually separate: correctness = "right actions",
    #     completeness = "all actions")
    completeness = correctness

    # 5. Timeliness = average timeliness across matched actions
    matched = [m for m in matches if m.agent_action is not None]
    timeliness = (sum(m.timeliness for m in matched) / len(matched)) if matched else 0.0

    # 6. Ordering
    ordering = score_ordering(matches, oracle_actions)

    # 7. Extra (spurious) actions
    matched_agent_count = sum(1 for m in matches if m.agent_action is not None)
    extra = max(0, len(agent_actions) - matched_agent_count)

    # 8. Weighted total
    total = (
        config.weight_correctness * correctness
        + config.weight_completeness * completeness
        + config.weight_timeliness * timeliness
        + config.weight_ordering * ordering
    )

    return ScoreResult(
        correctness=round(correctness, 4),
        completeness=round(completeness, 4),
        timeliness=round(timeliness, 4),
        ordering=round(ordering, 4),
        total=round(total, 4),
        matches=[m.to_dict() for m in matches],
        extra_actions=extra,
        config=asdict(config),
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 4:
        print("Usage: python action_scorer.py <events.jsonl> <oracle_actions.jsonl> <agent_actions.jsonl>")
        print("\nOptional: add --pretty for formatted output")
        sys.exit(1)

    events_path = sys.argv[1]
    oracle_path = sys.argv[2]
    agent_path = sys.argv[3]
    pretty = "--pretty" in sys.argv

    events = load_events(events_path)
    oracle_actions = load_actions(oracle_path)
    agent_actions = load_actions(agent_path)

    result = score(events, oracle_actions, agent_actions)

    if pretty:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(json.dumps(result.to_dict()))


if __name__ == "__main__":
    main()
