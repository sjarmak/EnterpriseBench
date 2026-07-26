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
V1_DIR = ROOT / "configs" / "studies" / "rryas_code_finder_canary_v1"
V2_DIR = ROOT / "configs" / "studies" / "rryas_code_finder_canary_v2"
CLI_V1_DIR = ROOT / "configs" / "studies" / "rryas_cli_code_finder_canary_v1"
TASK = ROOT / "benchmarks" / "dependency_management" / "dep-traversal-003" / "task.toml"
FINGERPRINT = (
    "sourcegraph-mcp-code-finder:exactly-once-per-repository:"
    "local-repos-denied:direct-tools-denied:beta-telemetry-required:"
    "proxy-v1:cli-equivalent-sgx-finder:v2"
)
CLI_FINGERPRINT = (
    "sourcegraph-cli-code-finder:exactly-once-per-repository:"
    "local-repos-denied:direct-tools-denied:beta-telemetry-required:"
    "proxy-v1:no-mcp-registration:v1"
)


def test_invalid_v1_capsule_remains_frozen_as_historical_evidence() -> None:
    manifest_path = V1_DIR / "canary_manifest.json"
    spec = StudySpec.load(V1_DIR / "study_spec.json")
    manifest = json.loads(manifest_path.read_text())

    assert spec.study_id == "rryas-code-finder-canary-v1"
    assert spec.task_manifest_hash == file_hash(manifest_path)
    assert spec.harness == manifest["harness_hash"]
    assert spec.revision == "264b547b18f0250e2703ca351aba0c6011b9b190"


def test_v2_canary_capsule_remains_frozen_as_valid_historical_evidence() -> None:
    manifest_path = V2_DIR / "canary_manifest.json"
    spec = StudySpec.load(V2_DIR / "study_spec.json")
    manifest = json.loads(manifest_path.read_text())
    assert ROOT / "agents" / "harnesses" / "mcp_telemetry_proxy.py" in (
        harness_input_paths(ROOT)
    )

    assert spec.study_id == "rryas-code-finder-canary-v2"
    assert spec.task_manifest_hash == file_hash(manifest_path)
    assert spec.task_ids == ("dep-traversal-003",)
    assert [(arm.name, arm.capability_fingerprint) for arm in spec.arms] == [
        ("mcp_code_finder", FINGERPRINT)
    ]
    assert spec.baseline_arm == "mcp_code_finder"
    assert spec.repetitions == 1
    assert spec.max_attempts == 1
    assert spec.promotion_policy == "validity-canary-only-no-comparison"
    assert spec.harness == manifest["harness_hash"]
    assert manifest["tasks"][0]["task_hash"] == (
        "sha256:1661f97c36ea0556a79088b8979bb8e9edabbe985d0204f3522fb221373d4b11"
    )
    assert manifest["verifier_hashes"]["dep-traversal-003"] == (
        "sha256:9e046e38c5a32ee17d591b91174cdaa7af47156de0decc4881407c33dde9f150"
    )


def test_canary_manifest_prespecifies_fail_closed_telemetry_and_cli_scope() -> None:
    manifest = json.loads((V2_DIR / "canary_manifest.json").read_text())
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
    assert manifest["judge_configuration"] == {
        "model": "cc:haiku",
        "account": 1,
        "executable": "claude-1",
        "selection": "explicit --judge-account 1",
        "provenance_required_in_scores": True,
    }
    assert manifest["supersedes"]["study_id"] == "rryas-code-finder-canary-v1"
    assert manifest["supersedes"]["evidence_policy"] == (
        "preserve the v1 receipt and artifacts unchanged"
    )


def test_cli_canary_capsule_locks_only_the_interface_change() -> None:
    manifest_path = CLI_V1_DIR / "canary_manifest.json"
    spec = StudySpec.load(CLI_V1_DIR / "study_spec.json")
    manifest = json.loads(manifest_path.read_text())
    provenance = capture_input_provenance(
        task_toml=TASK,
        harness_inputs=harness_input_paths(ROOT),
        verifier_inputs=verifier_input_paths(ROOT, TASK.parent),
        repo_root=ROOT,
    )

    assert spec.study_id == "rryas-cli-code-finder-canary-v1"
    assert spec.task_manifest_hash == file_hash(manifest_path)
    assert spec.task_ids == ("dep-traversal-003",)
    assert [(arm.name, arm.capability_fingerprint) for arm in spec.arms] == [
        ("cli_code_finder", CLI_FINGERPRINT)
    ]
    assert spec.baseline_arm == "cli_code_finder"
    assert spec.repetitions == 1
    assert spec.max_attempts == 1
    assert spec.model == "claude-sonnet-5"
    assert spec.promotion_policy == "validity-canary-only-no-comparison"
    assert spec.harness == provenance.harness_hash
    assert manifest["harness_hash"] == provenance.harness_hash
    assert manifest["tasks"][0]["task_hash"] == provenance.task_hash
    assert manifest["verifier_hashes"]["dep-traversal-003"] == (
        provenance.verifier_hash
    )


def test_cli_canary_manifest_is_matched_and_fails_closed() -> None:
    manifest = json.loads((CLI_V1_DIR / "canary_manifest.json").read_text())
    treatment = manifest["treatment"]

    assert manifest["matched_against"] == {
        "study_id": "rryas-code-finder-canary-v2",
        "trial": "dep-traversal-003/mcp_code_finder/rep1/attempt1",
        "task_id": "dep-traversal-003",
        "model": "claude-sonnet-5",
        "judge_model": "cc:haiku",
        "judge_account": 1,
        "comparison_scope": "interface_effect_only",
    }
    assert treatment == {
        "mode": "cli_code_finder",
        "capability_fingerprint": CLI_FINGERPRINT,
        "interface": "bash_composable_sgx_finder",
        "mcp_tools_registered": False,
        "code_finder_calls": "exactly_once_per_repository",
        "other_sgx_retrieval_allowed": False,
        "direct_sourcegraph_tools_allowed": False,
        "local_repository_source_readable": False,
        "required_telemetry": [
            "invocation_count",
            "repository_scope",
            "sourcegraphToolTelemetry",
            "tool_inventory_sha256",
            "code_finder_schema_sha256",
        ],
        "invalid_if": [
            "zero_or_wrong_code_finder_call_count",
            "interface_and_proxy_call_count_mismatch",
            "ambiguous_or_wrong_repository_scope",
            "any_other_sgx_retrieval_call",
            "any_direct_sourcegraph_retrieval_call",
            "failed_code_finder_response",
            "missing_sourcegraphToolTelemetry",
            "missing_or_malformed_proxy_trace",
        ],
    }
    assert manifest["judge_configuration"] == {
        "model": "cc:haiku",
        "account": 1,
        "executable": "claude-1",
        "selection": "explicit --judge-account 1",
        "provenance_required_in_scores": True,
    }
    assert manifest["execution_configuration"] == {
        "agent_account": 3,
        "timeout_seconds": 600,
        "build_timeout_seconds": 1800,
        "verifier_timeout_seconds": 600,
        "memory_mb": 8192,
        "no_build": True,
    }
    assert manifest["spend_guard"] == {
        "slots": 1,
        "max_attempts": 1,
        "dispatch_rule": "one matched CLI Finder validity slot only",
        "headline_eligible": False,
    }
