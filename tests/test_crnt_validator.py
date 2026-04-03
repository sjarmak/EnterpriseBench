"""Tests for the Cross-Repo Necessity Test (CRNT) validator."""

import json
import tempfile
from pathlib import Path

import pytest

from scripts.validation.crnt_validator import (
    AblatedConfig,
    CRNTResult,
    CheckpointInfo,
    RepoAblationResult,
    RepoInfo,
    compute_max_score_without_repo,
    evaluate_crnt,
    extract_checkpoints,
    extract_repos,
    format_result,
    generate_ablations,
    map_checkpoints_to_repos,
    main,
    parse_toml,
    write_ablated_configs,
)

# ── Fixtures ──────────────────────────────────────────────────────


def _make_multi_repo_config() -> dict:
    """A 3-repo task config where all checkpoints depend on all repos."""
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


def _make_partial_dependency_config() -> dict:
    """A 2-repo task where only one checkpoint depends on the second repo."""
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
                {"path": "lib/dep.py", "repo": "aux-repo"},
            ]
        },
    }


def _make_no_ground_truth_config() -> dict:
    """A multi-repo task with no ground_truth section."""
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


def _make_repo_deps_config() -> dict:
    """A 2-repo task where each checkpoint has explicit repo_deps."""
    return {
        "task": {"id": "test-repodeps-001", "suite": "dependency_management"},
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
            {
                "name": "cp_a",
                "weight": 0.5,
                "verifier": "checks/a.sh",
                "repo_deps": ["repo1"],
            },
            {
                "name": "cp_b",
                "weight": 0.5,
                "verifier": "checks/b.sh",
                "repo_deps": ["repo2"],
            },
        ],
        "ground_truth": {
            "required_files": [
                {"path": "src/main.py", "repo": "repo1"},
                {"path": "lib/dep.py", "repo": "repo2"},
            ]
        },
    }


def _make_mixed_config() -> dict:
    """A 2-repo task where one checkpoint has repo_deps, the other doesn't."""
    return {
        "task": {"id": "test-mixed-001", "suite": "feature_delivery"},
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
            {
                "name": "explicit_cp",
                "weight": 0.4,
                "verifier": "checks/explicit.sh",
                "repo_deps": ["repo1"],
            },
            {
                "name": "heuristic_cp",
                "weight": 0.6,
                "verifier": "checks/heuristic.sh",
            },
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

    def test_extracts_repo_deps(self) -> None:
        config = _make_repo_deps_config()
        cps = extract_checkpoints(config)
        assert cps[0].repo_deps == ("repo1",)
        assert cps[1].repo_deps == ("repo2",)

    def test_repo_deps_default_empty(self) -> None:
        config = _make_multi_repo_config()
        cps = extract_checkpoints(config)
        for cp in cps:
            assert cp.repo_deps == ()


# ── Test map_checkpoints_to_repos ────────────────────────────────


class TestMapCheckpointsToRepos:
    def test_all_repos_mapped(self) -> None:
        config = _make_multi_repo_config()
        mapping = map_checkpoints_to_repos(config)
        # All checkpoints should reference all 3 repos (since all 3 have required_files)
        for cp_name, repos in mapping.items():
            assert repos == {"alpha", "beta", "gamma"}

    def test_no_ground_truth_maps_to_all(self) -> None:
        config = _make_no_ground_truth_config()
        mapping = map_checkpoints_to_repos(config)
        for cp_name, repos in mapping.items():
            assert repos == {"a", "b"}

    def test_partial_dependency(self) -> None:
        config = _make_partial_dependency_config()
        mapping = map_checkpoints_to_repos(config)
        # Both checkpoints map to both repos since both repos have required_files
        for cp_name, repos in mapping.items():
            assert repos == {"main-repo", "aux-repo"}

    def test_repo_deps_anchors_to_declared_repos(self) -> None:
        config = _make_repo_deps_config()
        mapping = map_checkpoints_to_repos(config)
        assert mapping["cp_a"] == {"repo1"}
        assert mapping["cp_b"] == {"repo2"}

    def test_mixed_config_anchoring(self) -> None:
        config = _make_mixed_config()
        mapping = map_checkpoints_to_repos(config)
        # explicit_cp has repo_deps=["repo1"], anchored only to repo1
        assert mapping["explicit_cp"] == {"repo1"}
        # heuristic_cp has no repo_deps, falls back to gt_repos (both repos)
        assert mapping["heuristic_cp"] == {"repo1", "repo2"}


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


# ── Test compute_max_score_without_repo ──────────────────────────


class TestComputeMaxScore:
    def test_all_lost_when_all_depend(self) -> None:
        config = _make_multi_repo_config()
        score, lost = compute_max_score_without_repo(config, "alpha")
        assert score == 0.0
        assert set(lost) == {"cp1", "cp2", "cp3"}

    def test_no_ground_truth_all_lost(self) -> None:
        config = _make_no_ground_truth_config()
        score, lost = compute_max_score_without_repo(config, "a")
        assert score == 0.0
        assert len(lost) == 2

    def test_nonexistent_repo_no_loss(self) -> None:
        config = _make_multi_repo_config()
        score, lost = compute_max_score_without_repo(config, "nonexistent")
        assert score == pytest.approx(1.0)
        assert len(lost) == 0

    def test_repo_deps_removing_repo1_keeps_cp_b(self) -> None:
        """Removing repo1 loses cp_a (0.5) but keeps cp_b (0.5)."""
        config = _make_repo_deps_config()
        score, lost = compute_max_score_without_repo(config, "repo1")
        assert score == pytest.approx(0.5)
        assert lost == ("cp_a",)

    def test_repo_deps_removing_repo2_keeps_cp_a(self) -> None:
        """Removing repo2 loses cp_b (0.5) but keeps cp_a (0.5)."""
        config = _make_repo_deps_config()
        score, lost = compute_max_score_without_repo(config, "repo2")
        assert score == pytest.approx(0.5)
        assert lost == ("cp_b",)

    def test_mixed_config_removing_repo1(self) -> None:
        """Removing repo1 loses both checkpoints (explicit depends on repo1,
        heuristic depends on both repos including repo1)."""
        config = _make_mixed_config()
        score, lost = compute_max_score_without_repo(config, "repo1")
        assert score == pytest.approx(0.0)
        assert set(lost) == {"explicit_cp", "heuristic_cp"}

    def test_mixed_config_removing_repo2(self) -> None:
        """Removing repo2 keeps explicit_cp (repo_deps=repo1 only),
        loses heuristic_cp (depends on both repos)."""
        config = _make_mixed_config()
        score, lost = compute_max_score_without_repo(config, "repo2")
        assert score == pytest.approx(0.4)
        assert lost == ("heuristic_cp",)


# ── Test evaluate_crnt ───────────────────────────────────────────


class TestEvaluateCRNT:
    def test_multi_repo_passes(self) -> None:
        config = _make_multi_repo_config()
        result = evaluate_crnt(config)
        assert result.passes_crnt is True
        assert result.num_repos == 3

    def test_threshold_respected(self) -> None:
        config = _make_multi_repo_config()
        # With threshold=0.0, removing a repo gives score 0.0 which is ≤ 0.0
        result = evaluate_crnt(config, threshold=0.0)
        assert result.passes_crnt is True

    def test_task_id_extracted(self) -> None:
        config = _make_multi_repo_config()
        result = evaluate_crnt(config)
        assert result.task_id == "test-multi-001"

    def test_all_repo_results_present(self) -> None:
        config = _make_multi_repo_config()
        result = evaluate_crnt(config)
        assert len(result.repo_results) == 3

    def test_repo_deps_dual_repo_passes_crnt(self) -> None:
        """A dual-repo config with proper repo_deps passes CRNT because
        removing either repo drops max_score to 0.5 (≤ 0.6 threshold)."""
        config = _make_repo_deps_config()
        result = evaluate_crnt(config)
        assert result.passes_crnt is True
        # Each ablation should yield max_score=0.5
        for rr in result.repo_results:
            assert rr.max_score_without == pytest.approx(0.5)
            assert rr.passes_threshold is True

    def test_repo_deps_differentiated_scores(self) -> None:
        """Removing repo1 vs repo2 loses different checkpoints."""
        config = _make_repo_deps_config()
        result = evaluate_crnt(config)
        rr_by_repo = {rr.removed_repo.path: rr for rr in result.repo_results}
        assert rr_by_repo["repo1"].lost_checkpoints == ("cp_a",)
        assert rr_by_repo["repo2"].lost_checkpoints == ("cp_b",)


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
    def test_dry_run(self, capsys: pytest.CaptureFixture[str]) -> None:
        task_path = Path("benchmarks/dependency_management/dep-traversal-001/task.toml")
        if not task_path.exists():
            pytest.skip("dep-traversal-001 task.toml not found")
        ret = main(["str(task_path)", "--dry-run"])
        # Will fail because path doesn't exist as string — use real path
        ret = main([str(task_path), "--dry-run"])
        assert ret == 0
        captured = capsys.readouterr()
        assert "Ablation" in captured.out

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
        # Create a minimal single-repo TOML
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
