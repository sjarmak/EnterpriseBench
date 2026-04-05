"""Tests for verify_grounding.py — verifier grounding validator."""

import json
from pathlib import Path

import pytest

from scripts.validation.verify_grounding import (
    GroundingResult,
    evaluate_grounding,
    format_grounding_json,
    format_grounding_report,
    load_ablation_results,
    main,
)


def _make_dual_repo_config() -> dict:
    return {
        "task": {"id": "test-dual-001"},
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
                "role": "dependency",
            },
        ],
        "checkpoints": [
            {"name": "cp1", "weight": 0.5, "verifier": "checks/cp1.sh"},
            {"name": "cp2", "weight": 0.5, "verifier": "checks/cp2.sh"},
        ],
        "ground_truth": {
            "required_files": [
                {"path": "src/main.py", "repo": "a"},
                {"path": "lib/dep.py", "repo": "b"},
            ]
        },
    }


def _make_partial_config() -> dict:
    """Only one repo has required_files."""
    return {
        "task": {"id": "test-partial-001"},
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
                "role": "dependency",
            },
        ],
        "checkpoints": [
            {"name": "cp1", "weight": 1.0, "verifier": "checks/cp1.sh"},
        ],
        "ground_truth": {
            "required_files": [
                {"path": "src/main.py", "repo": "a"},
            ]
        },
    }


class TestEvaluateGrounding:
    def test_static_both_covered(self) -> None:
        config = _make_dual_repo_config()
        results = evaluate_grounding(config)
        assert len(results) == 2
        assert all(r.grounding_valid for r in results)

    def test_static_partial_coverage(self) -> None:
        config = _make_partial_config()
        results = evaluate_grounding(config)
        by_repo = {r.repo_path: r for r in results}
        assert by_repo["a"].grounding_valid is True
        assert by_repo["b"].grounding_valid is False

    def test_with_ablation_degraded(self) -> None:
        config = _make_dual_repo_config()
        ablation = {"a": 0.5, "b": 0.3}
        results = evaluate_grounding(config, ablation)
        assert all(r.grounding_valid for r in results)
        by_repo = {r.repo_path: r for r in results}
        assert by_repo["a"].ablation_score == 0.5
        assert by_repo["b"].ablation_score == 0.3

    def test_with_ablation_not_degraded(self) -> None:
        config = _make_dual_repo_config()
        ablation = {"a": 1.0, "b": 0.3}
        results = evaluate_grounding(config, ablation)
        by_repo = {r.repo_path: r for r in results}
        assert by_repo["a"].grounding_valid is False
        assert by_repo["b"].grounding_valid is True

    def test_ablation_missing_repo(self) -> None:
        config = _make_dual_repo_config()
        ablation = {"a": 0.5}
        results = evaluate_grounding(config, ablation)
        by_repo = {r.repo_path: r for r in results}
        assert by_repo["a"].ablation_score == 0.5
        assert by_repo["b"].ablation_score is None


class TestFormatReport:
    def test_pass_report(self) -> None:
        config = _make_dual_repo_config()
        results = evaluate_grounding(config)
        text = format_grounding_report(results)
        assert "Grounded:" in text
        assert "2/2" in text

    def test_fail_report(self) -> None:
        config = _make_partial_config()
        results = evaluate_grounding(config)
        text = format_grounding_report(results)
        assert "1/2" in text

    def test_empty(self) -> None:
        text = format_grounding_report(())
        assert "No repos" in text


class TestFormatJSON:
    def test_json_structure(self) -> None:
        config = _make_dual_repo_config()
        results = evaluate_grounding(config)
        data = json.loads(format_grounding_json(results))
        assert data["summary"]["total_repos"] == 2
        assert data["summary"]["all_grounded"] is True
        assert len(data["results"]) == 2


class TestLoadAblationResults:
    def test_empty_dir(self, tmp_path: Path) -> None:
        assert load_ablation_results(tmp_path) == {}

    def test_nonexistent_dir(self, tmp_path: Path) -> None:
        assert load_ablation_results(tmp_path / "nope") == {}

    def test_loads_scores(self, tmp_path: Path) -> None:
        ablate_dir = tmp_path / "ablate-myrepo" / "rep1"
        ablate_dir.mkdir(parents=True)
        results = {
            "scores": {
                "checkpoints": [
                    {"name": "cp1", "weight": 0.5, "score": 0.0},
                    {"name": "cp2", "weight": 0.5, "score": 1.0},
                ]
            }
        }
        (ablate_dir / "results.json").write_text(json.dumps(results))
        data = load_ablation_results(tmp_path)
        assert "myrepo" in data
        assert data["myrepo"] == pytest.approx(0.5)

    def test_averages_reps(self, tmp_path: Path) -> None:
        for rep in [1, 2]:
            d = tmp_path / "ablate-x" / f"rep{rep}"
            d.mkdir(parents=True)
            score = 0.4 if rep == 1 else 0.6
            results = {
                "scores": {
                    "checkpoints": [
                        {"name": "cp1", "weight": 1.0, "score": score},
                    ]
                }
            }
            (d / "results.json").write_text(json.dumps(results))
        data = load_ablation_results(tmp_path)
        assert data["x"] == pytest.approx(0.5)


class TestCLI:
    def test_real_task(self, capsys: pytest.CaptureFixture[str]) -> None:
        task_dir = Path("benchmarks/incident_response/incident-investigation-004")
        if not (task_dir / "task.toml").exists():
            pytest.skip("task not found")
        ret = main([str(task_dir)])
        assert ret == 0
        captured = capsys.readouterr()
        assert "Grounded" in captured.out

    def test_json_flag(self, capsys: pytest.CaptureFixture[str]) -> None:
        task_dir = Path("benchmarks/incident_response/incident-investigation-004")
        if not (task_dir / "task.toml").exists():
            pytest.skip("task not found")
        ret = main([str(task_dir), "--json"])
        assert ret == 0
        data = json.loads(capsys.readouterr().out)
        assert data["summary"]["all_grounded"] is True

    def test_nonexistent(self) -> None:
        ret = main(["/nonexistent/task"])
        assert ret == 1
