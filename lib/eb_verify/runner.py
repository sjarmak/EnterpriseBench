"""
Checkpoint runner: parses task.toml, executes verifiers in order, collects scores.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Optional

from eb_verify.task_parser import TaskDefinition, Checkpoint
from eb_verify.scoring import (
    CheckpointResult,
    VerificationResult,
    compute_score,
    write_reward,
)
from eb_verify.plugins import get_validator


class CheckpointRunner:
    """Runs checkpoints for a task definition and produces a VerificationResult."""

    def __init__(
        self,
        task: TaskDefinition,
        task_dir: Optional[Path] = None,
        workspace: Optional[Path] = None,
    ):
        self.task = task
        # task_dir is where the task.toml lives (verifier paths are relative to this)
        self.task_dir = (task_dir or Path(".")).resolve()
        # workspace is where repos are cloned
        self.workspace = (workspace or task.workspace_root).resolve()

    def sandbox_health_check(self) -> bool:
        """Check that all required repos exist under workspace."""
        for repo in self.task.repos:
            repo_path = self.workspace / repo.path
            if not repo_path.is_dir():
                print(f"[health] MISSING repo: {repo_path}")
                return False
            print(f"[health] OK: {repo_path}")
        return True

    def _safe_verifier_path(self, verifier: str) -> Path:
        """Resolve verifier path and assert it stays within task_dir."""
        resolved = (self.task_dir / verifier).resolve()
        if not str(resolved).startswith(str(self.task_dir) + "/") and resolved != self.task_dir:
            raise ValueError(
                f"Verifier path escapes task_dir: {verifier!r} -> {resolved}"
            )
        return resolved

    def run_checkpoint(self, checkpoint: Checkpoint) -> CheckpointResult:
        """Execute a single checkpoint verifier script and collect results."""
        try:
            verifier_path = self._safe_verifier_path(checkpoint.verifier)
        except ValueError as e:
            return CheckpointResult(
                name=checkpoint.name,
                weight=checkpoint.weight,
                passed=False,
                score=0.0,
                detail=str(e),
            )

        if not verifier_path.exists():
            return CheckpointResult(
                name=checkpoint.name,
                weight=checkpoint.weight,
                passed=False,
                score=0.0,
                detail=f"Verifier script not found: {verifier_path}",
            )

        env = os.environ.copy()
        env["WORKSPACE"] = str(self.workspace)
        env["TASK_DIR"] = str(self.task_dir)
        env["TASK_ID"] = self.task.id

        try:
            result = subprocess.run(
                ["bash", str(verifier_path)],
                capture_output=True,
                text=True,
                timeout=checkpoint.timeout_seconds,
                cwd=str(self.workspace),
                env=env,
            )

            # Convention: verifier prints JSON to stdout with {"score": 0.0-1.0, "detail": "..."}
            # If no JSON, use exit code: 0=pass (1.0), nonzero=fail (0.0)
            stdout = result.stdout.strip()
            try:
                data = json.loads(stdout)
                score = max(0.0, min(1.0, float(data.get("score", 0.0))))
                detail = data.get("detail", "")
                passed = score > 0.0
            except (json.JSONDecodeError, ValueError):
                passed = result.returncode == 0
                score = 1.0 if passed else 0.0
                detail = stdout or result.stderr.strip()

            return CheckpointResult(
                name=checkpoint.name,
                weight=checkpoint.weight,
                passed=passed,
                score=score,
                detail=detail,
            )
        except subprocess.TimeoutExpired:
            return CheckpointResult(
                name=checkpoint.name,
                weight=checkpoint.weight,
                passed=False,
                score=0.0,
                detail=f"Verifier timed out ({checkpoint.timeout_seconds}s)",
            )
        except Exception as e:
            return CheckpointResult(
                name=checkpoint.name,
                weight=checkpoint.weight,
                passed=False,
                score=0.0,
                detail=f"Error running verifier: {e}",
            )

    def validate_artifacts(self) -> list[dict]:
        """Validate all required artifacts using plugin validators."""
        results = []
        for artifact_type in self.task.artifacts.required:
            validator = get_validator(artifact_type)
            if validator is None:
                results.append({
                    "type": artifact_type,
                    "valid": False,
                    "detail": f"No validator registered for type: {artifact_type}",
                })
                continue
            result = validator.validate(self.workspace)
            results.append({
                "type": artifact_type,
                "valid": result.valid,
                "detail": result.detail,
            })
        return results

    def run_all(self, output_path: str | Path = "reward.txt") -> VerificationResult:
        """Run full verification: health check, checkpoints, artifacts, scoring."""
        # Health check (non-fatal in prototype — repos may not be cloned)
        healthy = self.sandbox_health_check()
        if not healthy:
            print("[runner] WARNING: sandbox health check failed, continuing anyway")

        # Run checkpoints in order
        checkpoint_results = []
        for cp in self.task.checkpoints:
            print(f"[runner] Running checkpoint: {cp.name}")
            result = self.run_checkpoint(cp)
            checkpoint_results.append(result)
            status = "PASS" if result.passed else "FAIL"
            print(f"[runner]   {status} score={result.score:.2f}")

        # Validate artifacts
        artifact_results = self.validate_artifacts()

        # Compute score
        total = compute_score(checkpoint_results)

        verification = VerificationResult(
            task_id=self.task.id,
            checkpoint_results=checkpoint_results,
            artifact_results=artifact_results,
            total_score=total,
        )

        # Write reward.txt
        reward_path = write_reward(verification, output_path)
        print(f"[runner] Wrote {reward_path} — total_score={total:.4f}")

        return verification

    def run_single(self, checkpoint_name: str) -> CheckpointResult:
        """Run a single checkpoint by name."""
        for cp in self.task.checkpoints:
            if cp.name == checkpoint_name:
                return self.run_checkpoint(cp)
        raise ValueError(f"Checkpoint not found: {checkpoint_name}")
