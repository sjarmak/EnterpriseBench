from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
for import_path in (
    PROJECT_ROOT / "lib",
    PROJECT_ROOT / "scripts" / "infra",
    PROJECT_ROOT / "scripts" / "orchestration",
    PROJECT_ROOT / "scripts" / "studies",
):
    sys.path.insert(0, str(import_path))

import build_generated_harness_parity_capsule as builder_module  # noqa: E402
from build_generated_harness_parity_capsule import (  # noqa: E402
    build_core_payloads,
    configured_revision,
    write_capsule,
)
from generated_harness_parity_preflight import (  # noqa: E402
    CAPSULE_ID,
    CODEX_STUDY_ID,
    OPENCODE_STUDY_ID,
    TASK_ID,
)


def _head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_builder_freezes_current_descriptive_no_spend_capsule() -> None:
    build = build_core_payloads(PROJECT_ROOT, revision=_head())

    assert build.manifest["capsule_id"] == CAPSULE_ID
    assert build.manifest["status"] == "locked-no-spend-capsule"
    assert build.manifest["tasks"][0]["task_id"] == TASK_ID
    assert (
        build.manifest["comparison_policy"]["cross_bundle"]
        == "descriptive only because harness and model identity jointly vary"
    )
    assert build.manifest["spend_guard"]["paid_dispatch_authorized"] is False
    assert build.codex_spec["study_id"] == CODEX_STUDY_ID
    assert build.opencode_spec["study_id"] == OPENCODE_STUDY_ID
    assert build.codex_spec["revision"] == _head()
    assert build.opencode_spec["revision"] == _head()
    assert build.codex_spec["harness"] == build.manifest["harness_hash"]
    assert build.opencode_spec["harness"] == build.manifest["harness_hash"]
    assert build.preflight_evidence["revision"] == _head()
    assert len(build.preflight_evidence["slots"]) == 4
    assert build.preflight_evidence["paid_dispatch_authorized"] is False


def test_builder_returns_json_without_aliasing_locked_contracts() -> None:
    first = build_core_payloads(PROJECT_ROOT, revision=_head())
    assert json.loads(json.dumps(first.manifest)) == first.manifest

    first.manifest["spend_guard"]["paid_dispatch_authorized"] = True
    second = build_core_payloads(PROJECT_ROOT, revision=_head())

    assert second.manifest["spend_guard"]["paid_dispatch_authorized"] is False


def test_capsule_write_check_and_revision_are_exact(tmp_path: Path) -> None:
    build = build_core_payloads(PROJECT_ROOT, revision=_head())
    write_capsule(tmp_path, build, check=False)

    write_capsule(tmp_path, build, check=True)
    assert configured_revision(tmp_path) == _head()

    manifest = (
        tmp_path
        / "configs"
        / "studies"
        / "rryas_generated_harness_finder_parity_v1"
        / "parity_manifest.json"
    )
    manifest.write_text("{}\n")
    with pytest.raises(ValueError, match="capsule drifted"):
        write_capsule(tmp_path, build, check=True)


def test_capsule_writer_rejects_symlinked_directory(
    tmp_path: Path,
) -> None:
    build = build_core_payloads(PROJECT_ROOT, revision=_head())
    trusted_parent = tmp_path / "configs" / "studies"
    trusted_parent.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (trusted_parent / "rryas_generated_harness_finder_parity_v1").symlink_to(
        outside, target_is_directory=True
    )

    with pytest.raises(RuntimeError, match="symlink|non-directory"):
        write_capsule(tmp_path, build, check=False)

    assert not any(outside.iterdir())


@pytest.mark.parametrize("check", (False, True))
def test_capsule_writer_rejects_symlinked_artifact(
    tmp_path: Path,
    check: bool,
) -> None:
    build = build_core_payloads(PROJECT_ROOT, revision=_head())
    write_capsule(tmp_path, build, check=False)
    manifest = (
        tmp_path
        / "configs"
        / "studies"
        / "rryas_generated_harness_finder_parity_v1"
        / "parity_manifest.json"
    )
    manifest.unlink()
    victim = tmp_path / "victim.json"
    victim.write_text("outside\n")
    manifest.symlink_to(victim)

    with pytest.raises(RuntimeError, match="single-link regular"):
        write_capsule(tmp_path, build, check=check)

    assert victim.read_text() == "outside\n"


@pytest.mark.parametrize("check", (False, True))
def test_capsule_writer_rejects_hardlinked_artifact(
    tmp_path: Path,
    check: bool,
) -> None:
    build = build_core_payloads(PROJECT_ROOT, revision=_head())
    write_capsule(tmp_path, build, check=False)
    manifest = (
        tmp_path
        / "configs"
        / "studies"
        / "rryas_generated_harness_finder_parity_v1"
        / "parity_manifest.json"
    )
    outside_link = tmp_path / "outside-link.json"
    os.link(manifest, outside_link)
    original = outside_link.read_bytes()

    with pytest.raises(RuntimeError, match="single-link regular"):
        write_capsule(tmp_path, build, check=check)

    assert outside_link.read_bytes() == original


@pytest.mark.parametrize("check", (False, True))
def test_capsule_writer_rejects_fifo_artifact(
    tmp_path: Path,
    check: bool,
) -> None:
    build = build_core_payloads(PROJECT_ROOT, revision=_head())
    write_capsule(tmp_path, build, check=False)
    manifest = (
        tmp_path
        / "configs"
        / "studies"
        / "rryas_generated_harness_finder_parity_v1"
        / "parity_manifest.json"
    )
    manifest.unlink()
    os.mkfifo(manifest)

    with pytest.raises(RuntimeError, match="single-link regular"):
        write_capsule(tmp_path, build, check=check)


def test_capsule_writer_cleans_temporary_after_write_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = build_core_payloads(PROJECT_ROOT, revision=_head())

    def fail_write(_descriptor: int, _source: memoryview) -> int:
        raise OSError("synthetic write failure")

    monkeypatch.setattr(builder_module.os, "write", fail_write)
    with pytest.raises(OSError, match="synthetic write failure"):
        write_capsule(tmp_path, build, check=False)

    capsule_dir = (
        tmp_path / "configs" / "studies" / "rryas_generated_harness_finder_parity_v1"
    )
    assert list(capsule_dir.iterdir()) == []


@pytest.mark.parametrize("entry_type", ("symlink", "fifo"))
def test_configured_revision_rejects_nonregular_spec(
    tmp_path: Path,
    entry_type: str,
) -> None:
    build = build_core_payloads(PROJECT_ROOT, revision=_head())
    write_capsule(tmp_path, build, check=False)
    spec = (
        tmp_path
        / "configs"
        / "studies"
        / "rryas_generated_harness_finder_parity_v1"
        / "codex_study_spec.json"
    )
    source = spec.read_bytes()
    spec.unlink()
    if entry_type == "symlink":
        victim = tmp_path / "outside-spec.json"
        victim.write_bytes(source)
        spec.symlink_to(victim)
    else:
        os.mkfifo(spec)

    with pytest.raises(RuntimeError, match="single-link regular"):
        configured_revision(tmp_path)
