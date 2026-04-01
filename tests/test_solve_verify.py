"""Tests for scripts/solve_verify.py — classification, loading, verification, reporting."""

from __future__ import annotations

import json
import os
import tempfile

import pytest

# Import the module under test
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from solve_verify import (
    GroundTruthFile,
    SolveVerificationReport,
    TaskInfo,
    VerificationResult,
    classify_parser,
    compare_with_bash_scores,
    generate_report,
    load_scored_results,
    load_task_toml,
    verify_file_language_consistency,
    verify_ground_truth_structure,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_task(
    task_id: str = "test-001",
    suite: str = "customer_escalation",
    task_type: str = "error_provenance",
    languages: list[str] | None = None,
    required_files: list[GroundTruthFile] | None = None,
    sufficient_files: list[GroundTruthFile] | None = None,
) -> TaskInfo:
    return TaskInfo(
        task_id=task_id,
        suite=suite,
        task_type=task_type,
        languages=languages if languages is not None else ["python"],
        difficulty="medium",
        ground_truth_tiers=["deterministic"],
        required_files=(
            required_files
            if required_files is not None
            else [
                GroundTruthFile(
                    path="src/app/main.py",
                    repo="myrepo",
                    confidence=0.95,
                    source="deterministic",
                )
            ]
        ),
        sufficient_files=sufficient_files if sufficient_files is not None else [],
        toml_path="/fake/path/task.toml",
    )


# ---------------------------------------------------------------------------
# Classification tests
# ---------------------------------------------------------------------------


class TestClassifyParser:
    def test_python(self) -> None:
        task = _make_task(languages=["python"])
        assert classify_parser(task) == "python_ast"

    def test_go(self) -> None:
        task = _make_task(languages=["go"])
        assert classify_parser(task) == "go_ast"

    def test_javascript(self) -> None:
        task = _make_task(languages=["javascript"])
        assert classify_parser(task) == "manifests"

    def test_typescript(self) -> None:
        task = _make_task(languages=["typescript"])
        assert classify_parser(task) == "manifests"

    def test_java(self) -> None:
        task = _make_task(languages=["java"])
        assert classify_parser(task) == "manifests"

    def test_multi_language_first_match(self) -> None:
        task = _make_task(languages=["python", "go"])
        assert classify_parser(task) == "python_ast"

    def test_yaml_structural(self) -> None:
        task = _make_task(languages=["yaml"])
        assert classify_parser(task) == "structural"

    def test_cpp_structural(self) -> None:
        task = _make_task(languages=["c++"])
        assert classify_parser(task) == "structural"

    def test_no_languages(self) -> None:
        task = _make_task(languages=[])
        assert classify_parser(task) == "none"

    def test_unknown_language(self) -> None:
        task = _make_task(languages=["cobol"])
        assert classify_parser(task) == "none"

    def test_mixed_known_unknown(self) -> None:
        task = _make_task(languages=["yaml", "go-template"])
        assert classify_parser(task) == "structural"

    def test_go_template_structural(self) -> None:
        task = _make_task(languages=["go-template"])
        assert classify_parser(task) == "structural"


# ---------------------------------------------------------------------------
# Ground truth structural verification
# ---------------------------------------------------------------------------


class TestVerifyGroundTruthStructure:
    def test_valid_task(self) -> None:
        task = _make_task(
            required_files=[
                GroundTruthFile("src/main.py", "myrepo", 0.95, "deterministic"),
            ],
        )
        result = verify_ground_truth_structure(task)
        assert result.status == "PASS"
        assert result.gt_verified_count == 1
        assert not result.gt_gaps

    def test_no_ground_truth_files(self) -> None:
        task = _make_task(required_files=[], sufficient_files=[])
        result = verify_ground_truth_structure(task)
        assert result.status == "GAP"
        assert "No ground truth files" in result.reason

    def test_no_parser_available(self) -> None:
        task = _make_task(
            languages=["cobol"],
            required_files=[
                GroundTruthFile("src/main.cob", "repo", 0.9, "det"),
            ],
        )
        result = verify_ground_truth_structure(task)
        assert result.status == "SKIP"

    def test_empty_path(self) -> None:
        task = _make_task(
            required_files=[
                GroundTruthFile("", "myrepo", 0.95, "det"),
            ],
        )
        result = verify_ground_truth_structure(task)
        assert result.status == "FAIL"
        assert any("Empty path" in g for g in result.gt_gaps)

    def test_empty_repo(self) -> None:
        task = _make_task(
            required_files=[
                GroundTruthFile("src/main.py", "", 0.95, "det"),
            ],
        )
        result = verify_ground_truth_structure(task)
        assert result.status == "FAIL"
        assert any("Empty repo" in g for g in result.gt_gaps)

    def test_invalid_confidence(self) -> None:
        task = _make_task(
            required_files=[
                GroundTruthFile("src/main.py", "repo", 1.5, "det"),
            ],
        )
        result = verify_ground_truth_structure(task)
        assert result.status == "FAIL"
        assert any("Invalid confidence" in g for g in result.gt_gaps)

    def test_duplicate_claim(self) -> None:
        task = _make_task(
            required_files=[
                GroundTruthFile("src/main.py", "repo", 0.9, "det"),
                GroundTruthFile("src/main.py", "repo", 0.8, "det"),
            ],
        )
        result = verify_ground_truth_structure(task)
        assert result.status == "PASS"  # 1 verified, 1 dup
        assert result.gt_verified_count == 1
        assert any("Duplicate" in g for g in result.gt_gaps)

    def test_path_lacks_extension(self) -> None:
        task = _make_task(
            required_files=[
                GroundTruthFile("Makefile", "repo", 0.9, "det"),
            ],
        )
        result = verify_ground_truth_structure(task)
        assert result.status == "FAIL"
        assert any("lacks extension" in g for g in result.gt_gaps)

    def test_mixed_valid_and_gaps(self) -> None:
        task = _make_task(
            required_files=[
                GroundTruthFile("src/main.py", "repo", 0.9, "det"),
                GroundTruthFile("", "repo", 0.9, "det"),
            ],
        )
        result = verify_ground_truth_structure(task)
        assert result.status == "PASS"
        assert result.gt_verified_count == 1
        assert len(result.gt_gaps) == 1

    def test_sufficient_files_included(self) -> None:
        task = _make_task(
            required_files=[
                GroundTruthFile("src/main.py", "repo", 0.9, "det"),
            ],
            sufficient_files=[
                GroundTruthFile("src/utils.py", "repo", 0.7, "det"),
            ],
        )
        result = verify_ground_truth_structure(task)
        assert result.status == "PASS"
        assert result.gt_file_count == 2
        assert result.gt_verified_count == 2


# ---------------------------------------------------------------------------
# Language consistency
# ---------------------------------------------------------------------------


class TestVerifyFileLanguageConsistency:
    def test_consistent_python(self) -> None:
        task = _make_task(
            languages=["python"],
            required_files=[
                GroundTruthFile("src/main.py", "repo", 0.9, "det"),
            ],
        )
        gaps = verify_file_language_consistency(task)
        assert not gaps

    def test_inconsistent_go_file_python_task(self) -> None:
        task = _make_task(
            languages=["python"],
            required_files=[
                GroundTruthFile("cmd/main.go", "repo", 0.9, "det"),
            ],
        )
        gaps = verify_file_language_consistency(task)
        assert len(gaps) == 1
        assert "inconsistent" in gaps[0]

    def test_json_is_universal(self) -> None:
        task = _make_task(
            languages=["python"],
            required_files=[
                GroundTruthFile("package.json", "repo", 0.9, "det"),
            ],
        )
        gaps = verify_file_language_consistency(task)
        assert not gaps

    def test_unknown_extension_no_gap(self) -> None:
        task = _make_task(
            languages=["python"],
            required_files=[
                GroundTruthFile("src/data.parquet", "repo", 0.9, "det"),
            ],
        )
        gaps = verify_file_language_consistency(task)
        assert not gaps


# ---------------------------------------------------------------------------
# Bash score comparison
# ---------------------------------------------------------------------------


class TestCompareWithBashScores:
    def test_enriches_result(self) -> None:
        result = VerificationResult(
            task_id="test-001",
            status="PASS",
            parser_type="python_ast",
            reason="ok",
        )
        scored = {"scores": {"task_score": 2.5, "all_passed": True}}
        result = compare_with_bash_scores(result, scored)
        assert result.bash_score == 2.5
        assert result.bash_passed is True

    def test_missing_scores(self) -> None:
        result = VerificationResult(
            task_id="test-001",
            status="PASS",
            parser_type="python_ast",
            reason="ok",
        )
        result = compare_with_bash_scores(result, {})
        assert result.bash_score == 0.0
        assert result.bash_passed is False


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


class TestGenerateReport:
    def test_basic_report(self) -> None:
        results = [
            VerificationResult(
                "t1",
                "PASS",
                "python_ast",
                "ok",
                suite="s1",
                task_type="tt1",
                languages=["python"],
            ),
            VerificationResult(
                "t2",
                "FAIL",
                "go_ast",
                "bad",
                suite="s1",
                task_type="tt2",
                languages=["go"],
            ),
            VerificationResult(
                "t3", "SKIP", "none", "skip", suite="s2", task_type="tt1", languages=[]
            ),
            VerificationResult(
                "t4",
                "GAP",
                "structural",
                "gap",
                suite="s2",
                task_type="tt2",
                languages=["yaml"],
            ),
        ]
        report = generate_report(results, total_scored=10)
        assert report.total_scored == 10
        assert report.total_checked == 4
        assert report.total_pass == 1
        assert report.total_fail == 1
        assert report.total_skip == 1
        assert report.total_gap == 1
        assert report.pass_rate == pytest.approx(0.5)

    def test_all_pass(self) -> None:
        results = [
            VerificationResult(
                "t1",
                "PASS",
                "python_ast",
                "ok",
                suite="s",
                task_type="t",
                languages=["py"],
            ),
            VerificationResult(
                "t2", "PASS", "go_ast", "ok", suite="s", task_type="t", languages=["go"]
            ),
        ]
        report = generate_report(results, total_scored=2)
        assert report.pass_rate == pytest.approx(1.0)

    def test_no_applicable(self) -> None:
        results = [
            VerificationResult(
                "t1", "SKIP", "none", "skip", suite="s", task_type="t", languages=[]
            ),
        ]
        report = generate_report(results, total_scored=1)
        assert report.pass_rate == pytest.approx(0.0)

    def test_by_suite_breakdown(self) -> None:
        results = [
            VerificationResult(
                "t1",
                "PASS",
                "python_ast",
                "ok",
                suite="customer_escalation",
                task_type="t",
                languages=["py"],
            ),
            VerificationResult(
                "t2",
                "FAIL",
                "python_ast",
                "bad",
                suite="customer_escalation",
                task_type="t",
                languages=["py"],
            ),
            VerificationResult(
                "t3",
                "PASS",
                "go_ast",
                "ok",
                suite="dependency_management",
                task_type="t",
                languages=["go"],
            ),
        ]
        report = generate_report(results, total_scored=3)
        assert report.by_suite["customer_escalation"]["PASS"] == 1
        assert report.by_suite["customer_escalation"]["FAIL"] == 1
        assert report.by_suite["dependency_management"]["PASS"] == 1

    def test_gaps_collected(self) -> None:
        r = VerificationResult(
            "t1", "PASS", "python_ast", "ok", suite="s", task_type="t", languages=["py"]
        )
        r.gt_gaps = ["gap1", "gap2"]
        report = generate_report([r], total_scored=1)
        assert len(report.ground_truth_gaps) == 2
        assert report.ground_truth_gaps[0]["task_id"] == "t1"


# ---------------------------------------------------------------------------
# Loading: task.toml
# ---------------------------------------------------------------------------


class TestLoadTaskToml:
    def test_load_valid_toml(self, tmp_path: str) -> None:
        toml_content = b"""
[task]
id = "test-001"
suite = "customer_escalation"
task_type = "error_provenance"
difficulty = "medium"

[metadata]
languages = ["python"]

[ground_truth]
tiers = ["deterministic"]

[[ground_truth.required_files]]
path = "src/main.py"
repo = "myrepo"
confidence = 0.95
source = "deterministic"
"""
        toml_path = os.path.join(str(tmp_path), "task.toml")
        with open(toml_path, "wb") as f:
            f.write(toml_content)

        task = load_task_toml(toml_path)
        assert task is not None
        assert task.task_id == "test-001"
        assert task.suite == "customer_escalation"
        assert task.languages == ["python"]
        assert len(task.required_files) == 1
        assert task.required_files[0].path == "src/main.py"

    def test_load_nonexistent(self) -> None:
        result = load_task_toml("/nonexistent/path/task.toml")
        assert result is None

    def test_load_no_task_id(self, tmp_path: str) -> None:
        toml_content = b"""
[task]
suite = "test"
"""
        toml_path = os.path.join(str(tmp_path), "task.toml")
        with open(toml_path, "wb") as f:
            f.write(toml_content)

        result = load_task_toml(toml_path)
        assert result is None


# ---------------------------------------------------------------------------
# Loading: scored results
# ---------------------------------------------------------------------------


class TestLoadScoredResults:
    def test_load_results(self, tmp_path: str) -> None:
        run_dir = os.path.join(str(tmp_path), "test-001")
        os.makedirs(run_dir)
        data = {
            "task_id": "test-001",
            "scores": {"task_score": 2.0, "all_passed": True},
        }
        with open(os.path.join(run_dir, "results.json"), "w") as f:
            json.dump(data, f)

        results = load_scored_results(str(tmp_path))
        assert "test-001" in results
        assert results["test-001"]["scores"]["task_score"] == 2.0

    def test_skip_underscore_dirs(self, tmp_path: str) -> None:
        run_dir = os.path.join(str(tmp_path), "_batch_summaries")
        os.makedirs(run_dir)
        with open(os.path.join(run_dir, "results.json"), "w") as f:
            json.dump({"task_id": "_batch"}, f)

        results = load_scored_results(str(tmp_path))
        assert len(results) == 0

    def test_skip_invalid_json(self, tmp_path: str) -> None:
        run_dir = os.path.join(str(tmp_path), "test-001")
        os.makedirs(run_dir)
        with open(os.path.join(run_dir, "results.json"), "w") as f:
            f.write("not json")

        results = load_scored_results(str(tmp_path))
        assert len(results) == 0
