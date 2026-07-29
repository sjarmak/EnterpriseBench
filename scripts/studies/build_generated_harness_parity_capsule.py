#!/usr/bin/env python3
"""Build the descriptive, no-spend generated-harness Finder capsule."""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess
import sys
import tomllib
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
for import_path in (
    REPO_ROOT,
    REPO_ROOT / "lib",
    REPO_ROOT / "scripts" / "infra",
    REPO_ROOT / "scripts" / "orchestration",
):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from eb_study import StudySpec, file_hash  # noqa: E402
from generated_harness_parity_preflight import (  # noqa: E402
    CAPSULE_ID,
    CODEX_STUDY_ID,
    OPENCODE_STUDY_ID,
    REPORT_PATH,
    REQUIRED_ARMS,
    REQUIRED_BUNDLES,
    REQUIRED_CACHE_ISOLATION,
    REQUIRED_COMPARISON_POLICY,
    REQUIRED_EXECUTION,
    REQUIRED_JUDGE,
    REQUIRED_PROMOTION_POLICY,
    REQUIRED_SLOTS,
    REQUIRED_SPEND_GUARD,
    REQUIRED_TREATMENT_CONTRACT,
    TASK_ID,
    GeneratedHarnessParityEvidence,
)
from mirror_naming import derive_mirror_name  # noqa: E402
from study_run import (  # noqa: E402
    capture_input_provenance,
    harness_input_paths,
    verifier_input_paths,
)

CONFIG_DIR = Path("configs/studies/rryas_generated_harness_finder_parity_v1")
TASK_TOML = Path("benchmarks/incident_response") / TASK_ID / "task.toml"
PURPOSE = (
    "Compare MCP Code Finder with the composable CLI Code Finder interface "
    "within two generated harness/model bundles. Cross-bundle results are "
    "descriptive because both harness and model identity vary."
)
_DIRECTORY_FLAGS = (
    os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
)
_FILE_READ_FLAGS = (
    os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
)
_FILE_WRITE_FLAGS = (
    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
)


@dataclass(frozen=True)
class CorePayloads:
    """The four immutable JSON payloads in the parity capsule."""

    manifest: dict[str, Any]
    codex_spec: dict[str, Any]
    opencode_spec: dict[str, Any]
    preflight_evidence: dict[str, Any]


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2) + "\n").encode()


def _payload_hash(payload: Mapping[str, Any]) -> str:
    return f"sha256:{hashlib.sha256(_json_bytes(payload)).hexdigest()}"


def _task_entry(repo_root: Path) -> tuple[dict[str, Any], tuple[str, ...], str, str]:
    task_path = repo_root / TASK_TOML
    with task_path.open("rb") as handle:
        task = tomllib.load(handle)
    repositories = tuple(
        f"github.com/{derive_mirror_name(repo['url'], repo['rev'])}"
        for repo in task["repos"]
    )
    provenance = capture_input_provenance(
        task_toml=task_path,
        harness_inputs=harness_input_paths(repo_root),
        verifier_inputs=verifier_input_paths(repo_root, task_path.parent),
        repo_root=repo_root,
    )
    task_hash = file_hash(task_path)
    if provenance.task_hash != task_hash:
        raise ValueError("generated-harness task provenance drifted")
    return (
        {
            "task_id": TASK_ID,
            "task_type": task["task"]["task_type"],
            "task_toml": str(TASK_TOML),
            "task_hash": task_hash,
            "graded_artifact_path": REPORT_PATH,
            "expected_repositories": list(repositories),
        },
        repositories,
        provenance.harness_hash,
        provenance.verifier_hash,
    )


def _bundle_payloads() -> list[dict[str, Any]]:
    output_roots = {
        "codex": "results/studies/rryas_codex_finder_parity_v1",
        "opencode": "results/studies/rryas_opencode_kimi_k3_finder_parity_v1",
    }
    return [
        {
            "harness": harness,
            "study_id": study_id,
            "model": model,
            "study_spec": str(CONFIG_DIR / f"{harness}_study_spec.json"),
            "output_root": output_roots[harness],
            "receipts": f"{output_roots[harness]}/receipts.jsonl",
        }
        for harness, study_id, model, _package in REQUIRED_BUNDLES
    ]


def _spec_payload(
    *,
    study_id: str,
    model: str,
    manifest_hash: str,
    harness_hash: str,
    revision: str,
) -> dict[str, Any]:
    return {
        "study_id": study_id,
        "schema_version": 1,
        "task_manifest_hash": manifest_hash,
        "task_ids": [TASK_ID],
        "arms": [
            {"name": name, "capability_fingerprint": fingerprint}
            for name, fingerprint in REQUIRED_ARMS
        ],
        "baseline_arm": "mcp_code_finder",
        "repetitions": 1,
        "attempt_policy": "first_valid_attempt",
        "max_attempts": 1,
        "model": model,
        "harness": harness_hash,
        "revision": revision,
        "token_source": "provider_native_usage",
        "score_contract": "weighted-mean-v2",
        "promotion_policy": REQUIRED_PROMOTION_POLICY,
    }


def build_core_payloads(repo_root: Path, *, revision: str) -> CorePayloads:
    """Derive the parity capsule without writing or launching a model."""

    repo_root = repo_root.resolve()
    task, repositories, harness_hash, verifier_hash = _task_entry(repo_root)
    bundles = _bundle_payloads()
    manifest = {
        "schema_version": 1,
        "status": "locked-no-spend-capsule",
        "capsule_id": CAPSULE_ID,
        "purpose": PURPOSE,
        "tasks": [task],
        "bundles": bundles,
        "treatment_contract": deepcopy(REQUIRED_TREATMENT_CONTRACT),
        "cache_isolation": deepcopy(REQUIRED_CACHE_ISOLATION),
        "judge_configuration": deepcopy(REQUIRED_JUDGE),
        "execution_configuration": deepcopy(REQUIRED_EXECUTION),
        "comparison_policy": deepcopy(REQUIRED_COMPARISON_POLICY),
        "spend_guard": deepcopy(REQUIRED_SPEND_GUARD),
        "harness_hash": harness_hash,
        "verifier_hashes": {TASK_ID: verifier_hash},
    }
    manifest_hash = _payload_hash(manifest)
    codex_spec = _spec_payload(
        study_id=CODEX_STUDY_ID,
        model=bundles[0]["model"],
        manifest_hash=manifest_hash,
        harness_hash=harness_hash,
        revision=revision,
    )
    opencode_spec = _spec_payload(
        study_id=OPENCODE_STUDY_ID,
        model=bundles[1]["model"],
        manifest_hash=manifest_hash,
        harness_hash=harness_hash,
        revision=revision,
    )
    codex = StudySpec.from_json(codex_spec)
    opencode = StudySpec.from_json(opencode_spec)
    evidence = GeneratedHarnessParityEvidence(
        capsule_id=CAPSULE_ID,
        spec_hashes=(
            (CODEX_STUDY_ID, codex.spec_hash),
            (OPENCODE_STUDY_ID, opencode.spec_hash),
        ),
        task_manifest_hash=manifest_hash,
        task_ids=(TASK_ID,),
        slots=REQUIRED_SLOTS,
        revision=revision,
        models=tuple((bundle["harness"], bundle["model"]) for bundle in bundles),
        mirror_repositories=repositories,
        output_roots=tuple(bundle["output_root"] for bundle in bundles),
        graded_artifact_path=REPORT_PATH,
        comparison_label="harness-model bundles; descriptive only",
        paid_dispatch_authorized=False,
    )
    return CorePayloads(
        manifest=manifest,
        codex_spec=codex_spec,
        opencode_spec=opencode_spec,
        preflight_evidence=asdict(evidence),
    )


def _open_capsule_directory(repo_root: Path, *, create: bool) -> int:
    try:
        current = os.open(repo_root, _DIRECTORY_FLAGS)
    except OSError as exc:
        raise RuntimeError("trusted repository root is not a real directory") from exc
    try:
        for part in CONFIG_DIR.parts:
            try:
                child = os.open(part, _DIRECTORY_FLAGS, dir_fd=current)
            except FileNotFoundError:
                if not create:
                    raise RuntimeError("capsule directory is missing") from None
                try:
                    os.mkdir(part, mode=0o700, dir_fd=current)
                    child = os.open(part, _DIRECTORY_FLAGS, dir_fd=current)
                except OSError as exc:
                    raise RuntimeError(
                        "cannot create capsule directory safely"
                    ) from exc
            except OSError as exc:
                raise RuntimeError(
                    "capsule path contains a symlink or non-directory"
                ) from exc
            os.close(current)
            current = child
        return current
    except BaseException:
        os.close(current)
        raise


def _read_regular_artifact(directory: int, name: str) -> bytes:
    try:
        descriptor = os.open(name, _FILE_READ_FLAGS, dir_fd=directory)
    except OSError as exc:
        raise RuntimeError(
            f"capsule artifact is not a single-link regular file: {name}"
        ) from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise RuntimeError(
                f"capsule artifact is not a single-link regular file: {name}"
            )
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, 1024 * 1024):
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _entry_exists(directory: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return True


def _write_regular_artifact(directory: int, name: str, source: bytes) -> None:
    if _entry_exists(directory, name):
        _read_regular_artifact(directory, name)
    temporary = f".{name}.{secrets.token_hex(12)}"
    descriptor = os.open(
        temporary,
        _FILE_WRITE_FLAGS,
        0o600,
        dir_fd=directory,
    )
    try:
        try:
            view = memoryview(source)
            while view:
                written = os.write(descriptor, view)
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.rename(
            temporary,
            name,
            src_dir_fd=directory,
            dst_dir_fd=directory,
        )
        os.fsync(directory)
    except BaseException:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass
        raise


def write_capsule(repo_root: Path, build: CorePayloads, *, check: bool) -> None:
    """Write or verify the generated-harness parity capsule."""

    payloads = {
        "parity_manifest.json": build.manifest,
        "codex_study_spec.json": build.codex_spec,
        "opencode_study_spec.json": build.opencode_spec,
        "preflight_evidence.json": build.preflight_evidence,
    }
    directory = _open_capsule_directory(repo_root, create=not check)
    try:
        for name, payload in payloads.items():
            expected = _json_bytes(payload)
            if check:
                if _read_regular_artifact(directory, name) != expected:
                    raise ValueError(
                        f"generated-harness capsule drifted: {CONFIG_DIR / name}"
                    )
            else:
                _write_regular_artifact(directory, name, expected)
    finally:
        os.close(directory)


def configured_revision(repo_root: Path) -> str:
    """Return the revision frozen in the committed Codex StudySpec."""

    directory = _open_capsule_directory(repo_root, create=False)
    try:
        source = _read_regular_artifact(directory, "codex_study_spec.json")
    finally:
        os.close(directory)
    try:
        payload = json.loads(source)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Codex StudySpec is not valid JSON") from exc
    return StudySpec.from_json(payload).revision


def _git_revision(repo_root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if committed parity artifacts differ; do not write files.",
    )
    args = parser.parse_args(argv)
    revision = (
        configured_revision(REPO_ROOT) if args.check else _git_revision(REPO_ROOT)
    )
    build = build_core_payloads(REPO_ROOT, revision=revision)
    write_capsule(REPO_ROOT, build, check=args.check)
    print(
        json.dumps(
            {
                "capsule_id": CAPSULE_ID,
                "revision": revision,
                "slots": len(REQUIRED_SLOTS),
                "comparison_label": (build.preflight_evidence["comparison_label"]),
                "paid_dispatch_authorized": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
