"""Tests for the Cross-Repo Necessity Test (CRNT) validator."""

import json
from pathlib import Path

import pytest

from scripts.validation.crnt_validator import (
    AblatedConfig,
    CRNTResult,
    CheckpointInfo,
    RepoFileCoverage,
    RepoInfo,
    evaluate_crnt,
    extract_checkpoints,
    extract_repos,
    format_result,
    generate_ablations,
    main,
    parse_toml,
    write_ablated_configs,
)

# ── Fixtures ──────────────────────────────────────────────────────


def _make_multi_repo_config() -> dict:
    """A 3-repo task config with required_files across all repos."""
    return {
        "task": {"id": "test-multi-001", "suite": "dependency_management"},
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
            {"name": "cp1", "weight": 0.4, "verifier": "checks/cp1.sh"},
            {"name": "cp2", "weight": 0.3, "verifier": "checks/cp2.sh"},
            {"name": "cp3", "weight": 0.3, "verifier": "checks/cp3.sh"},
        ],
        "ground_truth": {
            "required_files": [
                {"path": "src/main.py", "repo": "alpha"},
                {"path": "lib/util.py", "repo": "beta"},
                {"path": "config.yaml", "repo": "gamma"},
            ]
        },
    }


def _make_single_repo_config() -> dict:
    """A single-repo task config."""
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
        "ground_truth": {
            "required_files": [
                {"path": "main.py", "repo": "solo"},
            ]
        },
    }


def _make_partial_coverage_config() -> dict:
    """A 2-repo task where only one repo has required_files — should fail CRNT."""
    return {
        "task": {"id": "test-partial-001", "suite": "feature_delivery"},
        "repos": [
            {
                "url": "https://github.com/org/main-repo",
                "rev": "v1.0",
                "path": "main-repo",
                "role": "primary",
            },
            {
                "url": "https://github.com/org/aux-repo",
                "rev": "v1.0",
                "path": "aux-repo",
                "role": "dependency",
            },
        ],
        "checkpoints": [
            {"name": "core_analysis", "weight": 0.7, "verifier": "checks/core.sh"},
            {"name": "cross_repo_check", "weight": 0.3, "verifier": "checks/cross.sh"},
        ],
        "ground_truth": {
            "required_files": [
                {"path": "src/app.py", "repo": "main-repo"},
            ]
        },
    }


def _make_no_ground_truth_config() -> dict:
    """A multi-repo task with no ground_truth section — should fail CRNT."""
    return {
        "task": {"id": "test-nogt-001", "suite": "incident_response"},
        "repos": [
            {
                "url": "https://github.com/org/a",
                "rev": "v1",
                "path": "a",
                "role": "primary",
            },
            {
                "url": "https://github.com/org/b",
                "rev": "v1",
                "path": "b",
                "role": "consumer",
            },
        ],
        "checkpoints": [
            {"name": "cp1", "weight": 0.5, "verifier": "checks/cp1.sh"},
            {"name": "cp2", "weight": 0.5, "verifier": "checks/cp2.sh"},
        ],
    }


def _make_full_coverage_config() -> dict:
    """A 2-repo task where both repos have required_files — should pass CRNT."""
    return {
        "task": {"id": "test-full-001", "suite": "dependency_management"},
        "repos": [
            {
                "url": "https://github.com/org/repo1",
                "rev": "v1.0",
                "path": "repo1",
                "role": "primary",
            },
            {
                "url": "https://github.com/org/repo2",
                "rev": "v1.0",
                "path": "repo2",
                "role": "dependency",
            },
        ],
        "checkpoints": [
            {"name": "cp_a", "weight": 0.5, "verifier": "checks/a.sh"},
            {"name": "cp_b", "weight": 0.5, "verifier": "checks/b.sh"},
        ],
        "ground_truth": {
            "required_files": [
                {"path": "src/main.py", "repo": "repo1"},
                {"path": "lib/dep.py", "repo": "repo2"},
            ]
        },
    }


# ── Test extract_repos ────────────────────────────────────────────


class TestExtractRepos:
    def test_extracts_all_repos(self) -> None:
        config = _make_multi_repo_config()
        repos = extract_repos(config)
        assert len(repos) == 3
        assert repos[0].path == "alpha"
        assert repos[1].path == "beta"
        assert repos[2].path == "gamma"

    def test_repo_fields(self) -> None:
        config = _make_multi_repo_config()
        repos = extract_repos(config)
        assert repos[0].url == "https://github.com/org/alpha"
        assert repos[0].rev == "v1.0"
        assert repos[0].role == "primary"

    def test_empty_repos(self) -> None:
        repos = extract_repos({"repos": []})
        assert len(repos) == 0

    def test_missing_repos_key(self) -> None:
        repos = extract_repos({})
        assert len(repos) == 0


# ── Test extract_checkpoints ─────────────────────────────────────


class TestExtractCheckpoints:
    def test_extracts_all_checkpoints(self) -> None:
        config = _make_multi_repo_config()
        cps = extract_checkpoints(config)
        assert len(cps) == 3
        assert cps[0].name == "cp1"
        assert cps[0].weight == 0.4

    def test_weights_sum_to_one(self) -> None:
        config = _make_multi_repo_config()
        cps = extract_checkpoints(config)
        assert abs(sum(cp.weight for cp in cps) - 1.0) < 1e-9


# ── Test evaluate_crnt ───────────────────────────────────────────


class TestEvaluateCRNT:
    def test_multi_repo_all_covered_passes(self) -> None:
        config = _make_multi_repo_config()
        result = evaluate_crnt(config)
        assert result.passes_crnt is True
        assert result.num_repos == 3
        assert len(result.uncovered_repos) == 0

    def test_task_id_extracted(self) -> None:
        config = _make_multi_repo_config()
        result = evaluate_crnt(config)
        assert result.task_id == "test-multi-001"

    def test_all_repos_have_coverage(self) -> None:
        config = _make_multi_repo_config()
        result = evaluate_crnt(config)
        assert len(result.repo_coverage) == 3
        for rc in result.repo_coverage:
            assert rc.has_coverage is True
            assert rc.required_file_count >= 1

    def test_full_coverage_passes(self) -> None:
        config = _make_full_coverage_config()
        result = evaluate_crnt(config)
        assert result.passes_crnt is True

    def test_partial_coverage_fails(self) -> None:
        """A task where one repo has no required_files should fail CRNT."""
        config = _make_partial_coverage_config()
        result = evaluate_crnt(config)
        assert result.passes_crnt is False
        assert "aux-repo" in result.uncovered_repos

    def test_no_ground_truth_fails(self) -> None:
        """A task with no ground_truth section has no required_files coverage."""
        config = _make_no_ground_truth_config()
        result = evaluate_crnt(config)
        assert result.passes_crnt is False
        assert len(result.uncovered_repos) == 2

    def test_single_repo_fails(self) -> None:
        """Single-repo tasks cannot pass CRNT (requires >= 2 repos)."""
        config = _make_single_repo_config()
        result = evaluate_crnt(config)
        assert result.passes_crnt is False

    def test_file_counts_correct(self) -> None:
        config = _make_multi_repo_config()
        result = evaluate_crnt(config)
        counts = {rc.repo_path: rc.required_file_count for rc in result.repo_coverage}
        assert counts["alpha"] == 1
        assert counts["beta"] == 1
        assert counts["gamma"] == 1

    def test_multiple_files_per_repo(self) -> None:
        config = _make_multi_repo_config()
        config["ground_truth"]["required_files"].append(
            {"path": "extra.py", "repo": "alpha"}
        )
        result = evaluate_crnt(config)
        counts = {rc.repo_path: rc.required_file_count for rc in result.repo_coverage}
        assert counts["alpha"] == 2


# ── Test generate_ablations ──────────────────────────────────────


class TestGenerateAblations:
    def test_correct_count(self) -> None:
        config = _make_multi_repo_config()
        ablations = generate_ablations(config)
        assert len(ablations) == 3

    def test_each_removes_one_repo(self) -> None:
        config = _make_multi_repo_config()
        ablations = generate_ablations(config)
        removed_paths = {a.removed_repo.path for a in ablations}
        assert removed_paths == {"alpha", "beta", "gamma"}

    def test_remaining_repos_correct(self) -> None:
        config = _make_multi_repo_config()
        ablations = generate_ablations(config)
        for abl in ablations:
            assert len(abl.remaining_repos) == 2
            remaining_paths = {r.path for r in abl.remaining_repos}
            assert abl.removed_repo.path not in remaining_paths

    def test_to_dict_removes_repo(self) -> None:
        config = _make_multi_repo_config()
        ablations = generate_ablations(config)
        for abl in ablations:
            d = abl.to_dict()
            repo_paths = {r["path"] for r in d["repos"]}
            assert abl.removed_repo.path not in repo_paths
            assert len(d["repos"]) == 2

    def test_single_repo_ablation(self) -> None:
        config = _make_single_repo_config()
        ablations = generate_ablations(config)
        assert len(ablations) == 1
        assert len(ablations[0].remaining_repos) == 0


# ── Test format_result ───────────────────────────────────────────


class TestFormatResult:
    def test_pass_format(self) -> None:
        config = _make_multi_repo_config()
        result = evaluate_crnt(config)
        text = format_result(result)
        assert "PASS" in text
        assert "test-multi-001" in text

    def test_contains_repo_names(self) -> None:
        config = _make_multi_repo_config()
        result = evaluate_crnt(config)
        text = format_result(result)
        assert "alpha" in text
        assert "beta" in text
        assert "gamma" in text

    def test_fail_shows_uncovered(self) -> None:
        config = _make_partial_coverage_config()
        result = evaluate_crnt(config)
        text = format_result(result)
        assert "FAIL" in text
        assert "aux-repo" in text

    def test_file_counts_shown(self) -> None:
        config = _make_multi_repo_config()
        result = evaluate_crnt(config)
        text = format_result(result)
        assert "required_files=1" in text


# ── Test write_ablated_configs ───────────────────────────────────


class TestWriteAblatedConfigs:
    def test_writes_correct_files(self, tmp_path: Path) -> None:
        config = _make_multi_repo_config()
        ablations = generate_ablations(config)
        paths = write_ablated_configs(ablations, tmp_path)
        assert len(paths) == 3
        for p in paths:
            assert p.exists()
            data = json.loads(p.read_text())
            assert "repos" in data

    def test_filenames(self, tmp_path: Path) -> None:
        config = _make_multi_repo_config()
        ablations = generate_ablations(config)
        paths = write_ablated_configs(ablations, tmp_path)
        names = {p.name for p in paths}
        assert "test-multi-001_without_alpha.json" in names
        assert "test-multi-001_without_beta.json" in names
        assert "test-multi-001_without_gamma.json" in names


# ── Test parse_toml with real file ───────────────────────────────


class TestParseTOML:
    def test_parse_real_task(self) -> None:
        task_path = Path("benchmarks/dependency_management/dep-traversal-001/task.toml")
        if not task_path.exists():
            pytest.skip("dep-traversal-001 task.toml not found")
        config = parse_toml(task_path)
        assert config["task"]["id"] == "dep-traversal-001"
        assert len(config["repos"]) == 3

    def test_parse_nonexistent_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            parse_toml(Path("/nonexistent/task.toml"))


# ── Test CLI (main) ──────────────────────────────────────────────


class TestCLI:
    def test_json_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        task_path = Path("benchmarks/dependency_management/dep-traversal-001/task.toml")
        if not task_path.exists():
            pytest.skip("dep-traversal-001 task.toml not found")
        ret = main([str(task_path), "--json"])
        assert ret == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["task_id"] == "dep-traversal-001"
        assert data["passes_crnt"] is True

    def test_nonexistent_file(self) -> None:
        ret = main(["/nonexistent/task.toml"])
        assert ret == 1

    def test_single_repo_skips(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        toml_content = b"""
[task]
id = "single-001"
suite = "customer_escalation"

[[repos]]
url = "https://github.com/org/solo"
rev = "v1"
path = "solo"
"""
        toml_file = tmp_path / "task.toml"
        toml_file.write_bytes(toml_content)
        ret = main([str(toml_file)])
        assert ret == 0
        captured = capsys.readouterr()
        assert "1 repo" in captured.out
