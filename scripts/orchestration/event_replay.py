"""Event-replay runner for EnterpriseBench.

Feeds events to an agent and collects its actions, then scores them.

Agent interaction model (file-based):
  1. Runner writes events.jsonl into the sandbox at a known path.
  2. Agent reads events.jsonl at its own pace.
  3. Agent writes actions.jsonl with its responses.
  4. Runner reads actions.jsonl and scores against oracle.

This is simpler than streaming but still allows timeliness scoring because
the agent timestamps its own actions.  A future streaming mode could feed
events incrementally, but file-based is the pragmatic v1.

Usage:
    python event_replay.py <task_dir> [--agent-actions <path>]

    task_dir must contain:
      - task.toml (with session_type = "event_replay")
      - events.jsonl
      - oracle_actions.jsonl

    If --agent-actions is provided, score that file directly (useful for
    testing without running an actual agent).  Otherwise, the runner sets
    up the sandbox and waits for the agent to produce actions.jsonl.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running from scripts/orchestration/ directory
sys.path.insert(0, str(Path(__file__).parent))

from event_schema import (
    load_events,
    load_actions,
    validate_event_file,
    validate_action_file,
)
from action_scorer import score, ScoringConfig, ScoreResult


def load_task_config(task_dir: Path) -> dict:
    """Load and validate the task.toml file."""
    task_file = task_dir / "task.toml"
    if not task_file.exists():
        raise FileNotFoundError(f"No task.toml in {task_dir}")

    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore
        except ImportError:
            raise ImportError("Need Python 3.11+ (tomllib) or tomli package")

    with open(task_file, "rb") as f:
        config = tomllib.load(f)

    task = config.get("task", {})
    if task.get("session_type") != "event_replay":
        raise ValueError(
            f"Task {task.get('id', '???')} has session_type={task.get('session_type')}, "
            f"expected 'event_replay'"
        )

    return config


def resolve_paths(task_dir: Path, config: dict) -> tuple[Path, Path]:
    """Resolve event and oracle action file paths from task config."""
    events_cfg = config.get("events", {})

    event_file = task_dir / events_cfg.get("event_file", "events.jsonl")
    oracle_file = task_dir / events_cfg.get("oracle_actions", "oracle_actions.jsonl")

    if not event_file.exists():
        raise FileNotFoundError(f"Events file not found: {event_file}")
    if not oracle_file.exists():
        raise FileNotFoundError(f"Oracle actions file not found: {oracle_file}")

    return event_file, oracle_file


def run_scoring(
    events_path: Path,
    oracle_path: Path,
    agent_path: Path,
    config: ScoringConfig | None = None,
) -> ScoreResult:
    """Load files and run the scorer."""
    # Validate inputs
    event_errors = validate_event_file(events_path)
    if event_errors:
        print(f"WARNING: Event file validation issues:", file=sys.stderr)
        for e in event_errors:
            print(f"  - {e}", file=sys.stderr)

    action_errors = validate_action_file(agent_path)
    if action_errors:
        print(f"WARNING: Agent action file validation issues:", file=sys.stderr)
        for e in action_errors:
            print(f"  - {e}", file=sys.stderr)

    events = load_events(events_path)
    oracle_actions = load_actions(oracle_path)
    agent_actions = load_actions(agent_path)

    return score(events, oracle_actions, agent_actions, config)


def print_report(result: ScoreResult) -> None:
    """Print a human-readable scoring report."""
    print("=" * 60)
    print("  EVENT-REPLAY SCORING REPORT")
    print("=" * 60)
    print()
    print(f"  Correctness:  {result.correctness:.1%}  (weight: {result.config['weight_correctness']:.0%})")
    print(f"  Completeness: {result.completeness:.1%}  (weight: {result.config['weight_completeness']:.0%})")
    print(f"  Timeliness:   {result.timeliness:.1%}  (weight: {result.config['weight_timeliness']:.0%})")
    print(f"  Ordering:     {result.ordering:.1%}  (weight: {result.config['weight_ordering']:.0%})")
    print(f"  ──────────────────────────")
    print(f"  TOTAL SCORE:  {result.total:.1%}")
    print()

    if result.extra_actions > 0:
        print(f"  Extra (unmatched) agent actions: {result.extra_actions}")
        print()

    print("  Per-oracle-action breakdown:")
    for i, m in enumerate(result.matches, 1):
        oracle = m["oracle"]
        status = "MATCHED" if m["agent"] else "MISSED"
        print(f"    {i}. [{status}] {oracle['action_type']:12s} -> {oracle['target']}")
        if m["agent"]:
            print(f"       Timeliness: {m['timeliness']:.1%}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Event-replay runner and scorer")
    parser.add_argument("task_dir", type=Path, help="Path to task directory")
    parser.add_argument(
        "--agent-actions", type=Path, default=None,
        help="Path to agent's actions.jsonl (for offline scoring)"
    )
    parser.add_argument("--json", action="store_true", help="Output raw JSON instead of report")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    args = parser.parse_args()

    task_dir = args.task_dir.resolve()

    # Load task config
    config = load_task_config(task_dir)
    events_path, oracle_path = resolve_paths(task_dir, config)

    if args.agent_actions is None:
        # In a real run, we would:
        # 1. Set up sandbox with repos
        # 2. Copy events.jsonl into sandbox
        # 3. Run the agent with the task prompt
        # 4. Wait for agent to produce actions.jsonl
        # 5. Score the result
        #
        # For now, just print what would happen.
        print("Event-replay runner (sandbox integration not yet implemented)")
        print(f"  Task: {config['task']['id']}")
        print(f"  Events: {events_path} ({len(load_events(events_path))} events)")
        print(f"  Oracle: {oracle_path} ({len(load_actions(oracle_path))} actions)")
        print()
        print("To score an agent's output, re-run with --agent-actions <path>")
        return

    # Score mode
    agent_path = args.agent_actions.resolve()
    if not agent_path.exists():
        print(f"Agent actions file not found: {agent_path}", file=sys.stderr)
        sys.exit(1)

    result = run_scoring(events_path, oracle_path, agent_path)

    if args.json:
        indent = 2 if args.pretty else None
        print(json.dumps(result.to_dict(), indent=indent))
    else:
        print_report(result)


if __name__ == "__main__":
    main()
