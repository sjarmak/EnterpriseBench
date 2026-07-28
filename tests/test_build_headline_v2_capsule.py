from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for import_path in (
    PROJECT_ROOT / "lib",
    PROJECT_ROOT / "scripts" / "infra",
    PROJECT_ROOT / "scripts" / "orchestration",
    PROJECT_ROOT / "scripts" / "studies",
):
    sys.path.insert(0, str(import_path))

from build_headline_v2_capsule import (  # noqa: E402
    build_core_payloads,
    configured_revision,
    write_capsule,
)


def test_v2_builder_mechanically_excludes_only_exposed_tasks() -> None:
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    build = build_core_payloads(PROJECT_ROOT, revision=revision)

    assert len(build.manifest["tasks"]) == 40
    assert len(build.manifest["execution_configuration"]["execution_order"]) == 120
    assert build.manifest["selection"]["selected_count"] == 40
    assert build.spec["study_id"] == "rryas-headline-v2"
    assert build.spec["harness"] == build.manifest["harness_hash"]
    assert build.spec["arms"][-1]["capability_fingerprint"].endswith(
        "retrieval-before-local:cache-isolated:v3"
    )
    assert build.dispatch_plan["authorization"] == {
        "paid_dispatch_authorized": False,
        "authorization_reference": None,
    }
    assert build.dispatch_plan["cost_forecast"]["sample_attempts"] == 7
    assert build.canary["paid_dispatch_authorized"] is False
    assert build.canary["success_criterion"] == "sgx_tool_calls > 0"


def test_repository_v2_artifacts_are_current() -> None:
    revision = configured_revision(PROJECT_ROOT)
    build = build_core_payloads(PROJECT_ROOT, revision=revision)

    write_capsule(PROJECT_ROOT, build, check=True)
