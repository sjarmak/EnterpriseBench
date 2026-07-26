"""Locked no-comparison canary capsule for the Code Finder treatment."""

from __future__ import annotations

import json
from pathlib import Path

from eb_study import StudySpec, file_hash
from scripts.orchestration.study_run import (
    capture_input_provenance,
    harness_input_paths,
    verifier_input_paths,
)


ROOT = Path(__file__).resolve().parent.parent
STUDY_DIR = ROOT / "configs" / "studies" / "rryas_code_finder_canary_v1"
TASK = ROOT / "benchmarks" / "dependency_management" / "dep-traversal-003" / "task.toml"
FINGERPRINT = (
    "sourcegraph-mcp-code-finder:exactly-once-per-repository:"
    "local-repos-denied:direct-tools-denied:beta-telemetry-required:"
    "proxy-v1:cli-equivalent-sgx-finder:v2"
)


def test_canary_capsule_locks_treatment_and_current_inputs() -> None:
    manifest_path = STUDY_DIR / "canary_manifest.json"
    spec = StudySpec.load(STUDY_DIR / "study_spec.json")
    manifest = json.loads(manifest_path.read_text())
    provenance = capture_input_provenance(
        task_toml=TASK,
        harness_inputs=harness_input_paths(ROOT),
        verifier_inputs=verifier_input_paths(ROOT, TASK.parent),
        repo_root=ROOT,
    )
    assert ROOT / "agents" / "harnesses" / "mcp_telemetry_proxy.py" in (
        harness_input_paths(ROOT)
    )

    assert spec.study_id == "rryas-code-finder-canary-v1"
    assert spec.task_manifest_hash == file_hash(manifest_path)
    assert spec.task_ids == ("dep-traversal-003",)
    assert [(arm.name, arm.capability_fingerprint) for arm in spec.arms] == [
        ("mcp_code_finder", FINGERPRINT)
    ]
    assert spec.baseline_arm == "mcp_code_finder"
    assert spec.repetitions == 1
    assert spec.max_attempts == 2
    assert spec.promotion_policy == "validity-canary-only-no-comparison"
    assert spec.harness == provenance.harness_hash
    assert manifest["tasks"][0]["task_hash"] == provenance.task_hash
    assert manifest["verifier_hashes"]["dep-traversal-003"] == (
        provenance.verifier_hash
    )


def test_canary_manifest_prespecifies_fail_closed_telemetry_and_cli_scope() -> None:
    manifest = json.loads((STUDY_DIR / "canary_manifest.json").read_text())
    treatment = manifest["treatment"]

    assert treatment["mode"] == "mcp_code_finder"
    assert treatment["code_finder_calls"] == "exactly_once_per_repository"
    assert treatment["direct_sourcegraph_tools_allowed"] is False
    assert treatment["local_repository_source_readable"] is False
    assert treatment["required_telemetry"] == [
        "invocation_count",
        "repository_scope",
        "sourcegraphToolTelemetry",
        "tool_inventory_sha256",
        "code_finder_schema_sha256",
    ]
    assert treatment["invalid_if"] == [
        "zero_or_wrong_code_finder_call_count",
        "ambiguous_or_wrong_repository_scope",
        "any_direct_sourcegraph_retrieval_call",
        "failed_code_finder_response",
        "missing_sourcegraphToolTelemetry",
        "missing_or_malformed_proxy_trace",
    ]
    assert manifest["cli_comparability"] == {
        "current_cli_arm": "direct_sgx_plus_local_source",
        "code_finder_equivalent": "cli_code_finder",
        "equivalent_transport": "code_finder_via_sgx_no_mcp",
        "equivalent_contract": {
            "finder_calls": "exactly_once_per_repository",
            "other_sgx_retrieval_allowed": False,
            "local_repository_source_readable": False,
            "same_proxy_telemetry_required": True,
        },
        "analysis_rule": (
            "compare mcp_code_finder with cli_code_finder for interface effects; "
            "keep the direct cli arm as a separate retrieval treatment"
        ),
    }
