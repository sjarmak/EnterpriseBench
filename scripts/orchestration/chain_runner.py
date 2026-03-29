#!/usr/bin/env python3
"""
Session-chain orchestrator for EnterpriseBench.

Reads a chain task definition and executes N sessions sequentially,
with git-branch handoff and milestone verification between sessions.

Usage:
    python -m scripts.orchestration.chain_runner benchmarks/chain_example/task.toml
    python -m scripts.orchestration.chain_runner benchmarks/chain_example/task.toml --simulate
"""

import argparse
import json
import logging
import sys
import tempfile
from dataclasses import dataclass, field, asdict
from pathlib import Path

# Support both toml (Python 3.11+) and tomli
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

from .session import SessionConfig, SessionResult, run_session
from .milestone import SessionScore, run_session_milestones
from .branch_manager import list_session_branches

logger = logging.getLogger(__name__)


@dataclass
class ChainTaskDefinition:
    """Parsed chain task with per-session configuration."""
    task_id: str
    suite: str
    difficulty: str
    session_count: int
    repos: list[dict]
    sessions: list[SessionConfig]
    final_checkpoints: list[dict]
    metadata: dict = field(default_factory=dict)
    simulation: dict = field(default_factory=dict)


@dataclass
class ChainResult:
    """Complete result of running a chain task."""
    task_id: str
    session_results: list[SessionResult] = field(default_factory=list)
    milestone_scores: list[SessionScore] = field(default_factory=list)
    final_score: float = 0.0
    total_score: float = 0.0

    def summary(self) -> str:
        lines = [
            f"Chain Result: {self.task_id}",
            f"Sessions: {len(self.session_results)} / {len(self.session_results)}",
            "",
        ]
        for sr in self.session_results:
            status = "OK" if sr.success else f"FAIL ({sr.error})"
            branch = sr.branch_state.branch_name if sr.branch_state else "N/A"
            lines.append(f"  Session {sr.session_number}: {status} -> {branch}")

        lines.append("")
        for ms in self.milestone_scores:
            lines.append(f"  Session {ms.session_number} milestones: {ms.total_score:.2f}")
            for m in ms.milestones:
                status = "PASS" if m.passed else "FAIL"
                lines.append(f"    {m.milestone_name}: {status} ({m.score:.2f}) {m.message}")

        lines.append(f"\nFinal score: {self.final_score:.2f}")
        lines.append(f"Total score: {self.total_score:.2f}")
        return "\n".join(lines)


def parse_chain_task(toml_path: str) -> ChainTaskDefinition:
    """Parse a chain task.toml file into a ChainTaskDefinition."""
    path = Path(toml_path)
    if not path.exists():
        raise FileNotFoundError(f"Task file not found: {toml_path}")

    if tomllib is None:
        raise ImportError(
            "No TOML parser available. Install tomli (pip install tomli) "
            "or use Python 3.11+."
        )

    with open(path, "rb") as f:
        data = tomllib.load(f)

    task = data["task"]
    if task.get("session_type") != "chain":
        raise ValueError(f"Task {task['id']} is not a chain task (session_type={task.get('session_type')})")

    session_count = task.get("session_count", 2)

    # Parse per-session configs from [[sessions]] array
    sessions_data = data.get("sessions", [])
    sessions = []
    for i, s in enumerate(sessions_data):
        sessions.append(SessionConfig(
            session_number=i + 1,
            prompt=s["prompt"],
            milestones=s.get("milestones", []),
            context=s.get("context", {}),
        ))

    # Validate session count matches
    if len(sessions) != session_count:
        raise ValueError(
            f"session_count={session_count} but found {len(sessions)} [[sessions]] entries"
        )

    return ChainTaskDefinition(
        task_id=task["id"],
        suite=task["suite"],
        difficulty=task["difficulty"],
        session_count=session_count,
        repos=data.get("repos", []),
        sessions=sessions,
        final_checkpoints=data.get("checkpoints", []),
        metadata=data.get("metadata", {}),
        simulation=data.get("simulation", {}),
    )


def run_chain(
    task_def: ChainTaskDefinition,
    workspace_root: str | None = None,
    simulate: bool = False,
    agent_callable=None,
    task_dir: str = "",
) -> ChainResult:
    """Execute a full session chain.

    1. For each session:
       a. Set up workspace (fresh env with previous session's branch)
       b. Run agent or simulation
       c. Commit to session branch
       d. Run milestone verifiers (if not the last session)
    2. After all sessions: run final checkpoints, compute total score.
    """
    chain_result = ChainResult(task_id=task_def.task_id)

    if workspace_root is None:
        workspace_root = tempfile.mkdtemp(prefix=f"eb-chain-{task_def.task_id}-")

    logger.info("Starting chain: %s (%d sessions) in %s",
                task_def.task_id, task_def.session_count, workspace_root)

    previous_branch_state = None

    for session_config in task_def.sessions:
        session_num = session_config.session_number

        # Determine simulation actions for this session
        sim_actions = None
        if simulate and task_def.simulation:
            session_key = f"session_{session_num}"
            sim_actions = task_def.simulation.get(session_key, {}).get("actions", None)

        # Run the session
        session_result = run_session(
            session_config=session_config,
            repos=task_def.repos,
            task_id=task_def.task_id,
            workspace_root=workspace_root,
            previous_branch_state=previous_branch_state,
            simulation_actions=sim_actions,
            agent_callable=None if simulate else agent_callable,
        )
        chain_result.session_results.append(session_result)

        if not session_result.success:
            logger.error("Session %d failed, aborting chain.", session_num)
            break

        previous_branch_state = session_result.branch_state

        # Run milestones between sessions (not after the final one)
        if session_config.milestones and session_num < task_def.session_count:
            milestone_score = run_session_milestones(
                milestones=session_config.milestones,
                workspace_path=workspace_root,
                session_number=session_num,
                task_dir=task_dir,
            )
            chain_result.milestone_scores.append(milestone_score)

    # Run final checkpoints after the last session
    if task_def.final_checkpoints and chain_result.session_results:
        final_milestone = run_session_milestones(
            milestones=[
                {"name": cp["name"], "verifier": cp["verifier"]}
                for cp in task_def.final_checkpoints
            ],
            workspace_path=workspace_root,
            session_number=task_def.session_count,
            task_dir=task_dir,
        )
        chain_result.milestone_scores.append(final_milestone)

    # Compute total score
    _compute_total_score(chain_result, task_def)

    logger.info("Chain complete. Total score: %.2f", chain_result.total_score)
    return chain_result


def _compute_total_score(chain_result: ChainResult, task_def: ChainTaskDefinition):
    """Compute weighted total score from milestone results and final checkpoints."""
    # Milestone scores contribute proportionally
    all_milestone_results = []
    for ms in chain_result.milestone_scores:
        all_milestone_results.extend(ms.milestones)

    if not all_milestone_results:
        return

    # Final checkpoints have explicit weights; milestones are equal-weighted
    final_cp_names = {cp["name"] for cp in task_def.final_checkpoints}
    final_cp_weights = {cp["name"]: cp["weight"] for cp in task_def.final_checkpoints}

    weighted_sum = 0.0
    weight_sum = 0.0

    for mr in all_milestone_results:
        if mr.milestone_name in final_cp_weights:
            w = final_cp_weights[mr.milestone_name]
            weighted_sum += mr.score * w
            weight_sum += w
        else:
            # Inter-session milestones: small fixed weight
            w = 0.1
            weighted_sum += mr.score * w
            weight_sum += w

    chain_result.total_score = weighted_sum / weight_sum if weight_sum > 0 else 0.0
    chain_result.final_score = chain_result.total_score


def main():
    parser = argparse.ArgumentParser(description="Run a session-chain task")
    parser.add_argument("task_toml", help="Path to the chain task.toml file")
    parser.add_argument("--simulate", action="store_true",
                        help="Run in simulation mode (no real agent)")
    parser.add_argument("--workspace", default=None,
                        help="Workspace root directory (default: temp dir)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    task_def = parse_chain_task(args.task_toml)
    task_dir = str(Path(args.task_toml).parent.resolve())

    result = run_chain(
        task_def=task_def,
        workspace_root=args.workspace,
        simulate=args.simulate,
        task_dir=task_dir,
    )

    print("\n" + "=" * 60)
    print(result.summary())
    print("=" * 60)

    # Write result JSON
    result_path = Path(task_dir) / "chain_result.json"
    with open(result_path, "w") as f:
        json.dump({
            "task_id": result.task_id,
            "total_score": result.total_score,
            "sessions_completed": len([s for s in result.session_results if s.success]),
            "sessions_total": len(result.session_results),
        }, f, indent=2)
    print(f"\nResult written to: {result_path}")


if __name__ == "__main__":
    main()
