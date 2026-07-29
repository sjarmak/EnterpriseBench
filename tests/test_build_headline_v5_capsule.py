from __future__ import annotations

import json
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

from build_headline_v5_capsule import (  # noqa: E402
    build_core_payloads,
    configured_revision,
    write_capsule,
)
import build_headline_v5_capsule as v5_builder  # noqa: E402
import headline_protocol_evidence as protocol_evidence  # noqa: E402
from headline_protocol import V4_PROTOCOL, V5_PROTOCOL  # noqa: E402


def _head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_v5_preserves_v4_population_after_zero_agent_exposure() -> None:
    build = build_core_payloads(PROJECT_ROOT, revision=_head())
    v4_manifest = json.loads(
        (
            PROJECT_ROOT
            / "configs"
            / "studies"
            / V4_PROTOCOL.study_id
            / "final_manifest.json"
        ).read_text()
    )

    assert build.spec["study_id"] == V5_PROTOCOL.study_id
    assert build.spec["revision"] == _head()
    assert build.spec["task_ids"] == [
        task["task_id"] for task in v4_manifest["tasks"]
    ]
    for field in (
        "tasks",
        "arms",
        "cache_isolation",
        "judge_configuration",
        "evidence_policy",
    ):
        assert build.manifest[field] == v4_manifest[field]
    assert len(build.spec["task_ids"]) == 31
    assert len(build.manifest["execution_configuration"]["execution_order"]) == 93
    v5_order = build.manifest["execution_configuration"]["execution_order"]
    v4_order = v4_manifest["execution_configuration"]["execution_order"]
    assert [
        {**row, "output_dir": row["output_dir"].replace("v5", "v4")}
        for row in v5_order
    ] == v4_order
    assert build.analysis_plan["protocol_amendment"] == {
        "predecessor": "rryas-headline-v4",
        "reason": (
            "v4 stopped during run_task module import before agent startup"
        ),
        "selection_rule": (
            "retain the unchanged v4 population because v4 produced no agent "
            "output and exposed no task"
        ),
        "excluded_candidate_ids": [],
        "zero_agent_exposure_evidence": (
            "results/studies/rryas-headline-v4/batch-001-terminal.json"
        ),
        "zero_agent_exposure_evidence_sha256": (
            "sha256:05c65bb88a98276e4065c6eb3ab1cfe9bf18bfbdb68b3553b73adf0ecd10edb9"
        ),
        "predecessor_analysis_use": "operational evidence only",
    }
    assert build.dispatch_plan["provider_capacity"]["confirmed"] is False
    assert build.dispatch_plan["authorization"]["paid_dispatch_authorized"] is False
    v4_dispatch = json.loads(
        (
            PROJECT_ROOT
            / "configs"
            / "studies"
            / V4_PROTOCOL.study_id
            / "dispatch_plan.json"
        ).read_text()
    )
    assert build.dispatch_plan["batch_policy"] == v4_dispatch["batch_policy"]
    assert build.dispatch_plan["provider_capacity"] == v4_dispatch[
        "provider_capacity"
    ]


def test_repository_v5_artifacts_are_current() -> None:
    build = build_core_payloads(
        PROJECT_ROOT,
        revision=configured_revision(PROJECT_ROOT),
    )

    write_capsule(PROJECT_ROOT, build, check=True)


def test_v5_builder_rejects_changed_zero_exposure_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_file_hash = protocol_evidence.file_hash
    evidence_path = (
        PROJECT_ROOT
        / "results"
        / "studies"
        / "rryas-headline-v4"
        / "batch-001-terminal.json"
    ).resolve()

    def tampered_file_hash(path: Path) -> str:
        if path.resolve() == evidence_path:
            return f"sha256:{'0' * 64}"
        return real_file_hash(path)

    monkeypatch.setattr(protocol_evidence, "file_hash", tampered_file_hash)

    with pytest.raises(ValueError, match="zero-agent exposure evidence"):
        build_core_payloads(PROJECT_ROOT, revision=_head())


def test_terminal_v5_check_rejects_tampered_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_dir = tmp_path / v5_builder.V5_CONFIG_DIR
    config_dir.mkdir(parents=True)
    required = (
        "analysis_plan.json",
        "dispatch_plan.json",
        "final_manifest.json",
        "preflight_evidence.json",
        "study_spec.json",
    )
    for name in required:
        (config_dir / name).write_bytes(b"expected")
    (config_dir / "final_manifest.json").write_bytes(b"tampered")
    terminal = tmp_path / v5_builder.V5_TERMINAL
    terminal.parent.mkdir(parents=True)
    terminal.write_text("{}\n")
    monkeypatch.setattr(
        v5_builder,
        "_committed_capsule_bytes",
        lambda _root, _name: b"expected",
        raising=False,
    )

    with pytest.raises(ValueError, match="terminal v5 capsule artifact drifted"):
        write_capsule(tmp_path, object(), check=True)


def test_terminal_v5_write_mode_refuses_regeneration() -> None:
    build = build_core_payloads(PROJECT_ROOT, revision=_head())

    with pytest.raises(ValueError, match="terminal v5 capsule cannot be rewritten"):
        write_capsule(PROJECT_ROOT, build, check=False)
