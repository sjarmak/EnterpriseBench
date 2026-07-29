"""Git publication fixtures for paid-dispatch tests."""

from pathlib import Path
import subprocess


def publish_fixture(repo_root: Path) -> None:
    """Commit a fixture and publish it to a local bare origin/main."""

    subprocess.run(["git", "init", "-q"], cwd=repo_root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "eval@example.com"],
        cwd=repo_root,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Eval Test"],
        cwd=repo_root,
        check=True,
    )
    subprocess.run(["git", "add", "."], cwd=repo_root, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "published fixture"],
        cwd=repo_root,
        check=True,
    )
    remote_path = repo_root.with_name(f"{repo_root.name}-origin.git")
    subprocess.run(
        ["git", "init", "-q", "--bare", str(remote_path)],
        check=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", str(remote_path)],
        cwd=repo_root,
        check=True,
    )
    subprocess.run(
        ["git", "push", "-q", "origin", "HEAD:refs/heads/main"],
        cwd=repo_root,
        check=True,
    )
