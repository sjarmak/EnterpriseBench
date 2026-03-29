"""
Git branch management for session-chain handoff.

Handles branch creation, checkout, and state transfer between sessions.
Each session commits to: eb-chain-{task_id}-session-{N}
Next session checks out that branch as its starting state.
"""

import subprocess
import logging
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class BranchState:
    """Represents the git state at a branch handoff point."""
    branch_name: str
    commit_sha: str
    repo_path: str
    session_number: int


def branch_name_for_session(task_id: str, session_number: int) -> str:
    """Generate the canonical branch name for a given session."""
    return f"eb-chain-{task_id}-session-{session_number}"


def _run_git(repo_path: str, *args: str) -> subprocess.CompletedProcess:
    """Run a git command in the given repo directory."""
    cmd = ["git", "-C", repo_path] + list(args)
    logger.debug("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        logger.error("Git command failed: %s\nstderr: %s", " ".join(cmd), result.stderr)
    return result


def create_session_branch(repo_path: str, task_id: str, session_number: int) -> str:
    """Create a new branch for the given session.

    Returns the branch name.
    """
    branch = branch_name_for_session(task_id, session_number)
    result = _run_git(repo_path, "checkout", "-b", branch)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to create branch {branch}: {result.stderr}")
    logger.info("Created branch %s in %s", branch, repo_path)
    return branch


def checkout_session_branch(repo_path: str, task_id: str, session_number: int) -> str:
    """Check out an existing session branch.

    Returns the branch name.
    """
    branch = branch_name_for_session(task_id, session_number)
    result = _run_git(repo_path, "checkout", branch)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to checkout branch {branch}: {result.stderr}")
    logger.info("Checked out branch %s in %s", branch, repo_path)
    return branch


def commit_session_state(repo_path: str, task_id: str, session_number: int,
                         message: str | None = None) -> BranchState:
    """Stage all changes and commit on the current session branch.

    Returns BranchState with the commit SHA.
    """
    branch = branch_name_for_session(task_id, session_number)
    if message is None:
        message = f"Session {session_number} completed for task {task_id}"

    # Stage all changes
    _run_git(repo_path, "add", "-A")

    # Commit (allow empty for simulation purposes)
    result = _run_git(repo_path, "commit", "--allow-empty", "-m", message)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to commit: {result.stderr}")

    # Get commit SHA
    sha_result = _run_git(repo_path, "rev-parse", "HEAD")
    commit_sha = sha_result.stdout.strip()

    state = BranchState(
        branch_name=branch,
        commit_sha=commit_sha,
        repo_path=repo_path,
        session_number=session_number,
    )
    logger.info("Committed session %d state: %s (%s)", session_number, branch, commit_sha[:8])
    return state


def get_branch_diff(repo_path: str, base_branch: str, session_branch: str) -> str:
    """Get the diff between the base branch and a session branch."""
    result = _run_git(repo_path, "diff", f"{base_branch}...{session_branch}")
    return result.stdout


def list_session_branches(repo_path: str, task_id: str) -> list[str]:
    """List all session branches for a task, sorted by session number."""
    prefix = f"eb-chain-{task_id}-session-"
    result = _run_git(repo_path, "branch", "--list", f"{prefix}*")
    if result.returncode != 0:
        return []
    branches = [b.strip().lstrip("* ") for b in result.stdout.strip().split("\n") if b.strip()]
    branches.sort(key=lambda b: int(b.split("-session-")[-1]))
    return branches
