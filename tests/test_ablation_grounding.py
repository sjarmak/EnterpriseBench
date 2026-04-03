"""Tests for verify_grounding.py — verifier grounding validator."""

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from scripts.validation.verify_grounding import (
    GroundingExpectation,
    GroundingResult,
    evaluate_grounding,
    extract_checkpoint_repo_deps,
    format_grounding_json,
    format_grounding_report,
    identify_grounding_expectations,
    load_ablation_results,
    main,
)

# ── Fixtures ──────────────────────────────────────────────────────


def _make_dual_repo_config() -> dict[str, Any]:
    """A dual-repo task config with explicit repo_deps on checkpoints."""
    return {
        "task": {"id": "test-dual-001", "suite": "dependency_management"},
        "repos": [
            {
                "url": "https://github.com/org/frontend",
                "rev": "v1.0",
                "path": "frontend",
                "role": "primary",
            },
            {
                "url": "https://github.com/org/backend",
                "rev": "v2.0",
                "path": "backend",
                "role": "dependency",
            },
        ],
        "checkpoints": [
            {
                "name": "api_contract_check",
                "weight": 0.4,
                "verifier": "checks/api_contract.sh",
                "repo_deps": ["frontend", "backend"],
            },
            {
                "name": "frontend_routing",
                "weight": 0.3,
                "verifier": "checks/routing.sh",
                "repo_deps": ["frontend"],
            },
            {
                "name": "backend_schema",
                "weight": 0.3,
                "verifier": "checks/schema.sh",
                "repo_deps": ["backend"],
            },
        ],
    }


def _make_tri_repo_config() -> dict[str, Any]:
    """A tri-repo task config with mixed repo_deps."""
    return {
        "task": {"id": "test-tri-001", "suite": "incident_response"},
        "repos": [
            {
                "url": "https://github.com/org/alpha",
                "rev": "v1.0",
                "path": "alpha",
                "role": "primary",
            },
            {
                "url": "https://github.com/org/beta",
                "rev": "v2.0",
                "path": "beta",
                "role": "consumer",
            },
            {
                "url": "https://github.com/org/gamma",
                "rev": "v3.0",
                "path": "gamma",
                "role": "dependency",
            },
        ],
        "checkpoints": [
            {
                "name": "cross_repo_trace",
                "weight": 0.5,
                "verifier": "checks/trace.sh",
                "repo_deps": ["alpha", "beta", "gamma"],
            },
            {
                "name": "alpha_only",
                "weight": 0.3,
                "verifier": "checks/alpha.sh",
                "repo_deps": ["alpha"],
            },
            {
                "name": "beta_gamma",
                "weight": 0.2,
                "verifier": "checks/bg.sh",
                "repo_deps": ["beta", "gamma"],
            },
        ],
    }


def _make_no_repo_deps_config() -> dict[str, Any]:
    """A multi-repo config where checkpoints have NO explicit repo_deps.

    Falls back to ground_truth.required_files heuristic.
    """
    return {
        "task": {"id": "test-fallback-001", "suite": "feature_delivery"},
        "repos": [
            {
                "url": "https://github.com/org/svc-a",
                "rev": "v1.0",
                "path": "svc-a",
                "role": "primary",
            },
            {
                "url": "https://github.com/org/svc-b",
                "rev": "v2.0",
                "path": "svc-b",
                "role": "dependency",
            },
        ],
        "checkpoints": [
            {
                "name": "cp1",
                "weight": 0.5,
                "verifier": "checks/cp1.sh",
            },
            {
                "name": "cp2",
                "weight": 0.5,
                "verifier": "checks/cp2.sh",
            },
        ],
        "ground_truth": {
            "required_files": [
                {"path": "src/main.py", "repo": "svc-a"},
                {"path": "lib/util.py", "repo": "svc-b"},
            ]
        },
    }


def _make_single_repo_config() -> dict[str, Any]:
    """Single-repo config — grounding analysis should not apply."""
    return {
        "task": {"id": "test-single-001", "suite": "customer_escalation"},
        "repos": [
            {
                "url": "https://github.com/org/solo",
                "rev": "v1.0",
                "path": "solo",
                "role": "primary",
            },
        ],
        "checkpoints": [
            {"name": "cp1", "weight": 1.0, "verifier": "checks/cp1.sh"},
        ],
    }


# ── Tests: extract_checkpoint_repo_deps ───────────────────────────


class TestExtractCheckpointRepoDeps:
    def test_explicit_repo_deps(self) -> None:
        config = _make_dual_repo_config()
        deps = extract_checkpoint_repo_deps(config)

        assert deps["api_contract_check"] == {"frontend", "backend"}
        assert deps["frontend_routing"] == {"frontend"}
        assert deps["backend_schema"] == {"backend"}

    def test_fallback_to_ground_truth(self) -> None:
        config = _make_no_repo_deps_config()
        deps = extract_checkpoint_repo_deps(config)

        # Without repo_deps, falls back to ground_truth repos
        assert deps["cp1"] == {"svc-a", "svc-b"}
        assert deps["cp2"] == {"svc-a", "svc-b"}

    def test_tri_repo_mixed_deps(self) -> None:
        config = _make_tri_repo_config()
        deps = extract_checkpoint_repo_deps(config)

        assert deps["cross_repo_trace"] == {"alpha", "beta", "gamma"}
        assert deps["alpha_only"] == {"alpha"}
        assert deps["beta_gamma"] == {"beta", "gamma"}


# ── Tests: identify_grounding_expectations ────────────────────────


class TestIdentifyGroundingExpectations:
    def test_dual_repo_expectations(self) -> None:
        config = _make_dual_repo_config()
        expectations = identify_grounding_expectations(config)

        # api_contract_check -> 2 repos, frontend_routing -> 1, backend_schema -> 1
        assert len(expectations) == 4

        # All expectations should be expected_to_fail=True
        assert all(e.expected_to_fail for e in expectations)

        # Check specific expectations exist
        exp_tuples = {(e.checkpoint_name, e.anchored_repo) for e in expectations}
        assert ("api_contract_check", "frontend") in exp_tuples
        assert ("api_contract_check", "backend") in exp_tuples
        assert ("frontend_routing", "frontend") in exp_tuples
        assert ("backend_schema", "backend") in exp_tuples

    def test_weights_preserved(self) -> None:
        config = _make_dual_repo_config()
        expectations = identify_grounding_expectations(config)

        api_exps = [
            e for e in expectations if e.checkpoint_name == "api_contract_check"
        ]
        assert all(e.checkpoint_weight == 0.4 for e in api_exps)

    def test_tri_repo_expectation_count(self) -> None:
        config = _make_tri_repo_config()
        expectations = identify_grounding_expectations(config)

        # cross_repo_trace: 3 repos, alpha_only: 1, beta_gamma: 2
        assert len(expectations) == 6

    def test_single_repo_empty_expectations(self) -> None:
        """Single-repo tasks still produce expectations (anchored to the one repo)."""
        config = _make_single_repo_config()
        expectations = identify_grounding_expectations(config)

        # Single repo: cp1 is anchored to "solo" (fallback: all repos)
        assert len(expectations) == 1
        assert expectations[0].anchored_repo == "solo"


# ── Tests: evaluate_grounding ─────────────────────────────────────


class TestEvaluateGrounding:
    def test_static_analysis_all_valid(self) -> None:
        """Without ablation data, static analysis assumes all groundings are valid."""
        config = _make_dual_repo_config()
        results = evaluate_grounding(config, ablation_results=None)

        assert len(results) == 4
        assert all(r.grounding_valid for r in results)
        assert all("static analysis" in r.explanation for r in results)

    def test_with_matching_ablation_data(self) -> None:
        """When ablation data shows checkpoints fail as expected, all are valid."""
        config = _make_dual_repo_config()
        ablation_results = {
            "frontend": {
                "api_contract_check": True,  # failed as expected
                "frontend_routing": True,  # failed as expected
            },
            "backend": {
                "api_contract_check": True,  # failed as expected
                "backend_schema": True,  # failed as expected
            },
        }

        results = evaluate_grounding(config, ablation_results)
        assert all(r.grounding_valid for r in results)

    def test_with_mismatched_ablation_data(self) -> None:
        """When a checkpoint passes despite its repo being removed, grounding is invalid."""
        config = _make_dual_repo_config()
        ablation_results = {
            "frontend": {
                "api_contract_check": False,  # did NOT fail — bad grounding
                "frontend_routing": True,  # failed as expected
            },
            "backend": {
                "api_contract_check": True,
                "backend_schema": True,
            },
        }

        results = evaluate_grounding(config, ablation_results)

        invalid = [r for r in results if not r.grounding_valid]
        assert len(invalid) == 1
        assert invalid[0].checkpoint_name == "api_contract_check"
        assert invalid[0].anchored_repo == "frontend"
        assert "did NOT fail" in invalid[0].explanation

    def test_missing_repo_in_ablation_data(self) -> None:
        """When ablation data is missing for a repo, checkpoint is treated as not failed."""
        config = _make_dual_repo_config()
        # Only "frontend" ablation data available, "backend" missing
        ablation_results = {
            "frontend": {
                "api_contract_check": True,
                "frontend_routing": True,
            },
        }

        results = evaluate_grounding(config, ablation_results)

        # backend-anchored checkpoints should show as invalid (not failed = False)
        backend_results = [r for r in results if r.anchored_repo == "backend"]
        assert len(backend_results) == 2
        assert all(not r.grounding_valid for r in backend_results)


# ── Tests: format_grounding_json ──────────────────────────────────


class TestFormatGroundingJson:
    def test_json_structure(self) -> None:
        config = _make_dual_repo_config()
        results = evaluate_grounding(config, ablation_results=None)

        json_str = format_grounding_json(results)
        parsed = json.loads(json_str)

        assert "summary" in parsed
        assert "results" in parsed
        assert parsed["summary"]["total_expectations"] == 4
        assert parsed["summary"]["valid_groundings"] == 4
        assert parsed["summary"]["all_grounded"] is True

    def test_json_with_invalid_grounding(self) -> None:
        config = _make_dual_repo_config()
        ablation_results = {
            "frontend": {"api_contract_check": False, "frontend_routing": True},
            "backend": {"api_contract_check": True, "backend_schema": True},
        }

        results = evaluate_grounding(config, ablation_results)
        json_str = format_grounding_json(results)
        parsed = json.loads(json_str)

        assert parsed["summary"]["all_grounded"] is False
        assert parsed["summary"]["valid_groundings"] == 3

    def test_empty_results_json(self) -> None:
        results: tuple[GroundingResult, ...] = ()
        json_str = format_grounding_json(results)
        parsed = json.loads(json_str)

        assert parsed["summary"]["total_expectations"] == 0
        assert parsed["summary"]["all_grounded"] is True

    def test_json_result_fields(self) -> None:
        config = _make_dual_repo_config()
        results = evaluate_grounding(config, ablation_results=None)
        json_str = format_grounding_json(results)
        parsed = json.loads(json_str)

        first_result = parsed["results"][0]
        expected_keys = {
            "checkpoint",
            "anchored_repo",
            "expected_to_fail",
            "actually_failed",
            "grounding_valid",
            "explanation",
        }
        assert set(first_result.keys()) == expected_keys


# ── Tests: format_grounding_report ────────────────────────────────


class TestFormatGroundingReport:
    def test_report_header(self) -> None:
        config = _make_dual_repo_config()
        results = evaluate_grounding(config, ablation_results=None)
        report = format_grounding_report(results)

        assert "Verifier Grounding Report" in report
        assert "Total expectations: 4" in report
        assert "Valid groundings:   4/4" in report

    def test_empty_results_message(self) -> None:
        results: tuple[GroundingResult, ...] = ()
        report = format_grounding_report(results)

        assert "No grounding expectations found" in report

    def test_report_contains_checkpoint_names(self) -> None:
        config = _make_dual_repo_config()
        results = evaluate_grounding(config, ablation_results=None)
        report = format_grounding_report(results)

        assert "api_contract_check" in report
        assert "frontend_routing" in report
        assert "backend_schema" in report


# ── Tests: load_ablation_results ──────────────────────────────────


class TestLoadAblationResults:
    def test_load_from_directory(self, tmp_path: Path) -> None:
        # Create ablation directory structure
        ablate_dir = tmp_path / "ablate-frontend" / "rep1"
        ablate_dir.mkdir(parents=True)
        results_file = ablate_dir / "results.json"
        results_file.write_text(json.dumps({"scores": {"cp1": 0.0, "cp2": 1.0}}))

        loaded = load_ablation_results(tmp_path)

        assert "frontend" in loaded
        assert loaded["frontend"]["cp1"] is True  # score 0.0 = failed
        assert loaded["frontend"]["cp2"] is False  # score 1.0 = passed

    def test_load_multiple_reps(self, tmp_path: Path) -> None:
        # Rep 1: cp1 fails
        rep1 = tmp_path / "ablate-backend" / "rep1"
        rep1.mkdir(parents=True)
        (rep1 / "results.json").write_text(json.dumps({"scores": {"cp1": 0.0}}))

        # Rep 2: cp1 also fails
        rep2 = tmp_path / "ablate-backend" / "rep2"
        rep2.mkdir(parents=True)
        (rep2 / "results.json").write_text(json.dumps({"scores": {"cp1": 0.0}}))

        loaded = load_ablation_results(tmp_path)

        assert loaded["backend"]["cp1"] is True  # failed in all reps

    def test_load_mixed_reps(self, tmp_path: Path) -> None:
        """If a checkpoint fails in some reps but not all, it is not 'failed'."""
        rep1 = tmp_path / "ablate-backend" / "rep1"
        rep1.mkdir(parents=True)
        (rep1 / "results.json").write_text(json.dumps({"scores": {"cp1": 0.0}}))

        rep2 = tmp_path / "ablate-backend" / "rep2"
        rep2.mkdir(parents=True)
        (rep2 / "results.json").write_text(json.dumps({"scores": {"cp1": 0.5}}))

        loaded = load_ablation_results(tmp_path)

        # Not all reps failed, so conservative = not failed
        assert loaded["backend"]["cp1"] is False

    def test_load_nonexistent_dir(self, tmp_path: Path) -> None:
        loaded = load_ablation_results(tmp_path / "nonexistent")
        assert loaded == {}

    def test_load_empty_dir(self, tmp_path: Path) -> None:
        loaded = load_ablation_results(tmp_path)
        assert loaded == {}


# ── Tests: main CLI ───────────────────────────────────────────────


class TestMainCLI:
    def test_missing_task_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = main([str(Path(tmp) / "nonexistent")])
            assert result == 1

    def test_single_repo_exits_zero(self, tmp_path: Path) -> None:
        """Single-repo tasks should exit 0 with a message."""
        task_toml = tmp_path / "task.toml"
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore[no-redef]

        # Write a minimal single-repo task.toml
        task_toml.write_text(
            '[task]\nid = "single-001"\nsuite = "test"\n\n'
            '[[repos]]\nurl = "https://github.com/org/solo"\n'
            'rev = "v1.0"\npath = "solo"\nrole = "primary"\n\n'
            '[[checkpoints]]\nname = "cp1"\nweight = 1.0\n'
            'verifier = "checks/cp1.sh"\n'
        )

        result = main([str(tmp_path)])
        assert result == 0
