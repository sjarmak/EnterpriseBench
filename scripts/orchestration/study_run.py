"""Host-side provenance and receipt helpers for study-enabled task runs."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from eb_study import (
    CapsuleError,
    StudyCapsule,
    StudySpec,
    append_receipt,
    content_hash,
    file_hash,
    read_receipts,
)

try:
    from .study_receipt import SCORE_CONTRACT, RunEvidence, build_receipt
except ImportError:
    from study_receipt import SCORE_CONTRACT, RunEvidence, build_receipt

_IMAGE_ID_RE = re.compile(r"sha256:[0-9a-f]{64}")


@dataclass(frozen=True)
class InputProvenance:
    """Content identities for the task, harness, and verifier inputs."""

    task_hash: str
    harness_hash: str
    verifier_hash: str


def harness_input_paths(repo_root: Path) -> tuple[Path, ...]:
    """Return the complete source set whose bytes define the task harness."""

    return (
        repo_root / "scripts" / "orchestration",
        repo_root / "scripts" / "sandbox",
        repo_root / "scripts" / "lib",
        repo_root / "scripts" / "infra" / "create_sg_mirrors.py",
        repo_root / "scripts" / "cost_tracker.py",
        repo_root / "scripts" / "analyze_scores.py",
        repo_root / "lib" / "eb_verify",
        repo_root / "lib" / "eb_study",
        repo_root / "lib" / "pyproject.toml",
        repo_root / "agents" / "harnesses" / "claude",
    )


def verifier_input_paths(repo_root: Path, task_dir: Path) -> tuple[Path, ...]:
    """Return the shared and task-local verifier inputs for one trial."""

    paths = [
        repo_root / "scripts" / "sandbox" / "test_runner.sh",
        repo_root / "lib" / "eb_verify",
    ]
    for path in (task_dir / "checks", task_dir / "ground_truth.json"):
        if path.exists():
            paths.append(path)
    return tuple(paths)


def validate_study_config(
    *,
    study_spec: Path | None,
    study_receipts: Path | None,
    repetition: int | None,
    attempt: int | None,
    dry_run: bool,
) -> None:
    """Fail fast unless a study run has a complete trial identity."""

    if (study_spec is None) != (study_receipts is None):
        raise ValueError("study_spec and study_receipts must be configured together")
    if study_spec is None:
        if attempt is not None:
            raise ValueError("attempt requires study_spec and study_receipts")
        return
    if repetition is None or repetition < 1:
        raise ValueError("study runs require rep >= 1")
    if attempt is None or attempt < 1:
        raise ValueError("study runs require attempt >= 1")
    if dry_run:
        raise ValueError("dry_run cannot emit a study trial receipt")
    if not study_spec.is_file():
        raise ValueError(f"study_spec does not exist: {study_spec}")
    if not study_receipts.parent.is_dir():
        raise ValueError(
            f"study_receipts parent does not exist: {study_receipts.parent}"
        )
    try:
        spec = StudySpec.load(study_spec)
        if repetition > spec.repetitions:
            raise ValueError(
                f"rep {repetition} exceeds study repetitions {spec.repetitions}"
            )
        if attempt > spec.max_attempts:
            raise ValueError(
                f"attempt {attempt} exceeds study max_attempts {spec.max_attempts}"
            )
        if spec.score_contract != SCORE_CONTRACT:
            raise ValueError(
                f"study score_contract {spec.score_contract!r} does not match "
                f"runner contract {SCORE_CONTRACT!r}"
            )
        if study_receipts.exists():
            receipts = read_receipts(study_receipts)
            if receipts:
                StudyCapsule.build(spec, receipts)
    except CapsuleError as exc:
        raise ValueError(f"invalid study capsule configuration: {exc}") from exc


def docker_image_digest(
    image_tag: str,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> str:
    """Return Docker's immutable local image ID for an exact built tag."""

    runner = runner or subprocess.run
    result = runner(
        ["docker", "image", "inspect", "--format", "{{.Id}}", image_tag],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"docker image inspect failed for {image_tag}: {result.stderr.strip()}"
        )
    digest = result.stdout.strip()
    if _IMAGE_ID_RE.fullmatch(digest) is None:
        raise RuntimeError(
            f"docker image inspect returned an invalid image ID for {image_tag}"
        )
    return digest


def docker_container_image_digest(
    container_id: str,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> str:
    """Return the immutable image ID Docker bound to a created container."""

    runner = runner or subprocess.run
    result = runner(
        ["docker", "inspect", "--format", "{{.Image}}", container_id],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"docker inspect failed for container {container_id}: "
            f"{result.stderr.strip()}"
        )
    digest = result.stdout.strip()
    if _IMAGE_ID_RE.fullmatch(digest) is None:
        raise RuntimeError(
            f"docker inspect returned an invalid image ID for container {container_id}"
        )
    return digest


def capture_input_provenance(
    *,
    task_toml: Path,
    harness_inputs: Iterable[Path],
    verifier_inputs: Iterable[Path],
    repo_root: Path,
) -> InputProvenance:
    """Hash the exact host inputs copied or executed for one trial."""

    return InputProvenance(
        task_hash=file_hash(task_toml),
        harness_hash=_manifest_hash(harness_inputs, repo_root),
        verifier_hash=_manifest_hash(verifier_inputs, repo_root),
    )


def emit_study_receipt(
    *,
    spec_path: Path,
    receipts_path: Path,
    run_dir: Path,
    repetition: int,
    attempt: int,
    evidence: RunEvidence,
) -> None:
    """Append the finished run's immutable receipt to its named study."""

    spec = StudySpec.load(spec_path)
    receipt = build_receipt(
        spec,
        run_dir,
        repetition=repetition,
        attempt=attempt,
        evidence=evidence,
    )
    append_receipt(receipts_path, receipt)


def _manifest_hash(paths: Iterable[Path], repo_root: Path) -> str:
    entries: dict[str, str] = {}
    for source in sorted({Path(path) for path in paths}):
        candidates = (
            sorted(
                path
                for path in source.rglob("*")
                if path.is_file()
                and "__pycache__" not in path.parts
                and path.suffix != ".pyc"
            )
            if source.is_dir()
            else [source]
        )
        for path in candidates:
            if not path.is_file():
                raise FileNotFoundError(f"provenance input does not exist: {path}")
            try:
                name = str(path.resolve().relative_to(repo_root.resolve()))
            except ValueError:
                name = str(path.resolve())
            entries[name] = file_hash(path)
    if not entries:
        raise ValueError("provenance manifest contains no files")
    return content_hash(entries)


__all__ = [
    "InputProvenance",
    "capture_input_provenance",
    "docker_container_image_digest",
    "docker_image_digest",
    "emit_study_receipt",
    "harness_input_paths",
    "validate_study_config",
    "verifier_input_paths",
]
