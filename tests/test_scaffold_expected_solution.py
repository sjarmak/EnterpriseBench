"""Tests for scripts/validation/scaffold_expected_solution.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from textwrap import dedent

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts" / "validation"
sys.path.insert(0, str(SCRIPTS_DIR))

import scaffold_expected_solution as ses  # noqa: E402


@pytest.fixture
def std_incident_task(tmp_path: Path) -> Path:
    """Standard incident_investigation task: 4 standard checkpoints."""
    d = tmp_path / "incident-001"
    d.mkdir()
    (d / "task.toml").write_text(
        dedent(
            """
            [task]
            id = "incident-inv-test-001"
            suite = "incident_response"
            difficulty = "hard"
            session_type = "single"

            [[repos]]
            url = "https://github.com/foo/bar"
            rev = "v1.0.0"
            path = "bar"
            role = "primary"

            [[checkpoints]]
            name = "root_cause_identification"
            weight = 0.35
            verifier = "checks/check_root_cause.sh"

            [[checkpoints]]
            name = "error_chain_trace"
            weight = 0.30
            verifier = "checks/check_error_chain.sh"

            [[checkpoints]]
            name = "affected_services"
            weight = 0.15
            verifier = "checks/check_affected_services.sh"

            [[checkpoints]]
            name = "remediation_proposal"
            weight = 0.20
            verifier = "checks/check_remediation.sh"
            """
        ).strip()
    )
    (d / "ground_truth.json").write_text(
        json.dumps(
            {
                "candidate_id": "test",
                "repos": ["foo/bar"],
                "description": "watch cache misses delete events",
                "root_cause": {
                    "file": "src/storage/cacher.go",
                    "function": "processEvent",
                    "summary": "DELETE event reuses PrevObject's stale resourceVersion",
                    "mechanism": "switch case sends event.PrevObject.DeepCopyObject() without updating resourceVersion",
                },
                "error_chain": [
                    {
                        "component": "client-go informer",
                        "action": "watches with resourceVersion",
                    },
                    {
                        "component": "watch cache cacher.go",
                        "action": "BUG: PrevObject retains stale rv",
                    },
                ],
                "affected_services": [
                    "kube-apiserver watch cache",
                    "client-go informers",
                    "any namespace-scoped watch",
                ],
                "remediation": "Update copied object's resourceVersion to the event's rv before emitting.",
                "fix_files": ["src/storage/cacher.go"],
            }
        )
    )
    return d


def test_standard_checkpoints_get_drafted(std_incident_task: Path) -> None:
    """Standard incident_investigation checkpoints map cleanly from ground_truth."""
    payload = ses.scaffold(std_incident_task)
    assert payload["task_id"] == "incident-inv-test-001"
    cps = payload["checkpoints"]
    assert set(cps.keys()) == {
        "root_cause_identification",
        "error_chain_trace",
        "affected_services",
        "remediation_proposal",
    }
    # Each should have non-empty content drafted from ground_truth
    for name, body in cps.items():
        assert body["expected_solution"], f"{name} expected_solution empty"
        assert len(body["evaluation_criteria"]) >= 2, f"{name} too few criteria"
        # Standard scaffolds should NOT carry the curation flag
        assert body.get("_curation_required") is not True, (
            f"{name} should be auto-drafted, not flagged"
        )


def test_standard_root_cause_uses_ground_truth_file(std_incident_task: Path) -> None:
    payload = ses.scaffold(std_incident_task)
    rc = payload["checkpoints"]["root_cause_identification"]
    body = rc["expected_solution"] + " ".join(rc["evaluation_criteria"])
    assert "src/storage/cacher.go" in body
    assert "processEvent" in body


def test_custom_checkpoint_emits_curation_flag(tmp_path: Path) -> None:
    d = tmp_path / "custom-001"
    d.mkdir()
    (d / "task.toml").write_text(
        dedent(
            """
            [task]
            id = "custom-task-001"
            suite = "incident_response"
            difficulty = "hard"
            session_type = "single"

            [[repos]]
            url = "https://github.com/cortex/cortex"
            rev = "v1.0.0"
            path = "cortex"
            role = "primary"

            [[checkpoints]]
            name = "cortex_ring"
            weight = 0.4
            verifier = "checks/check_ring.sh"

            [[checkpoints]]
            name = "thanos_store"
            weight = 0.3
            verifier = "checks/check_store.sh"
            """
        ).strip()
    )
    (d / "ground_truth.json").write_text(
        json.dumps({"candidate_id": "x", "repos": ["cortex/cortex"]})
    )

    payload = ses.scaffold(d)
    for name in ["cortex_ring", "thanos_store"]:
        cp = payload["checkpoints"][name]
        assert cp["_curation_required"] is True
        assert cp["evaluation_criteria"]  # at least placeholder entries


def test_scaffold_includes_required_files_in_criteria(std_incident_task: Path) -> None:
    """ground_truth.required_files should propagate into evaluation_criteria."""
    # Add required_files to ground_truth
    gt_path = std_incident_task / "ground_truth.json"
    gt = json.loads(gt_path.read_text())
    gt["required_files"] = [
        {"path": "src/api/handler.go", "repo": "bar", "confidence": 0.9},
    ]
    gt_path.write_text(json.dumps(gt))

    payload = ses.scaffold(std_incident_task)
    affected = payload["checkpoints"]["affected_services"]
    crit_blob = " ".join(affected["evaluation_criteria"])
    # required_files paths should be visible somewhere in the affected_services criteria
    assert "src/api/handler.go" in crit_blob or any(
        "src/api/handler.go" in c
        for cp in payload["checkpoints"].values()
        for c in cp.get("evaluation_criteria", [])
    )


def test_missing_ground_truth_still_produces_curation_stubs(tmp_path: Path) -> None:
    """Tasks without ground_truth.json should still scaffold valid structure."""
    d = tmp_path / "no-gt-001"
    d.mkdir()
    (d / "task.toml").write_text(
        dedent(
            """
            [task]
            id = "no-gt-001"
            suite = "incident_response"
            difficulty = "hard"
            session_type = "single"

            [[repos]]
            url = "https://github.com/foo/bar"
            rev = "v1.0.0"
            path = "bar"
            role = "primary"

            [[checkpoints]]
            name = "root_cause_identification"
            weight = 0.4
            verifier = "checks/check.sh"

            [[checkpoints]]
            name = "remediation_proposal"
            weight = 0.3
            verifier = "checks/check.sh"
            """
        ).strip()
    )
    payload = ses.scaffold(d)
    for name, body in payload["checkpoints"].items():
        assert body["_curation_required"] is True
        assert body["evaluation_criteria"]


def test_scaffold_output_validates_against_validator(std_incident_task: Path) -> None:
    """Standard scaffold output should pass validate_expected_solutions structurally."""
    payload = ses.scaffold(std_incident_task)
    out = std_incident_task / "expected_solution.json"
    out.write_text(json.dumps(payload, indent=2))

    import validate_expected_solutions as ves  # noqa: E402

    result = ves.validate_task(std_incident_task)
    # Structural validity (criteria>=2, names match, task_id correct, no _curation_required flag)
    assert result.ok, result.errors
