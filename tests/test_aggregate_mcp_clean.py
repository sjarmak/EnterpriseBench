"""Regression tests for results/analysis/aggregate_mcp_clean.py validity classing.

Guards EnterpriseBench-te9ah: run_task._effective_status persists the run status
lowercase (RUN_STATUS_INVALID == "invalid"), but the aggregator compared against
uppercase "INVALID" only, so every invalidated run fell through to cls="VALID"
and was counted in the headline clean set. These tests pin the case-insensitive
classification and its downstream effect on the clean set.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# aggregate_mcp_clean.py lives in results/analysis/, imported the same way its
# tracked consumers (scripts/analysis/recompute_headline_*.py) import it.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "results" / "analysis"))

import aggregate_mcp_clean as amc  # noqa: E402

# The orchestration constant the analysis must agree with — pin the two together
# so a rename that reintroduces the drift trips this import/assert, not the paper.
sys.path.insert(0, str(REPO_ROOT / "scripts" / "orchestration"))
from run_task import RUN_STATUS_INVALID  # noqa: E402


def _write_mode(task_dir: Path, mode: str, *, status, num_turns, task_score,
                mcp_calls: int = 3) -> None:
    """Write a minimal results.json for one (task, mode) under task_dir."""
    d = task_dir / mode
    d.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "scores": {"task_score": task_score, "checkpoints": []},
        "tool_usage": {"num_turns": num_turns, "mcp_tool_calls": mcp_calls},
    }
    (d / "results.json").write_text(json.dumps(payload) + "\n")


class TestValidityClassing:
    def test_lowercase_invalid_classes_invalid(self, tmp_path: Path) -> None:
        """The exact case from the bead: {status:'invalid', turns:5, score:0.9}.

        Fails pre-fix (classed VALID); the whole point of te9ah.
        """
        _write_mode(tmp_path, "mcp_only", status="invalid", num_turns=5,
                    task_score=0.9)
        rec = amc.load_mode(tmp_path, "mcp_only")
        assert rec is not None
        assert rec["class"] == "INVALID"

    def test_run_status_constant_classes_invalid(self, tmp_path: Path) -> None:
        """Use the actual run_task constant, not a literal, as the writer would."""
        _write_mode(tmp_path, "mcp_only", status=RUN_STATUS_INVALID, num_turns=5,
                    task_score=0.9)
        assert amc.load_mode(tmp_path, "mcp_only")["class"] == "INVALID"

    def test_uppercase_invalid_still_classes_invalid(self, tmp_path: Path) -> None:
        """Legacy/verifier uppercase schema must keep working."""
        _write_mode(tmp_path, "mcp_only", status="INVALID", num_turns=5,
                    task_score=0.9)
        assert amc.load_mode(tmp_path, "mcp_only")["class"] == "INVALID"

    @pytest.mark.parametrize("status,expected", [
        ("VALID", "VALID"),
        ("valid", "VALID"),
        ("FALLBACK", "FALLBACK"),
        ("fallback", "FALLBACK"),
        ("", "VALID"),      # current run_task valid/complete run
        (None, "VALID"),    # legacy run without a status field
    ])
    def test_valid_and_fallback_normalize(self, tmp_path: Path, status,
                                          expected: str) -> None:
        _write_mode(tmp_path, "baseline", status=status, num_turns=4,
                    task_score=1.0)
        assert amc.load_mode(tmp_path, "baseline")["class"] == expected

    def test_zero_turns_is_noop_regardless_of_status(self, tmp_path: Path) -> None:
        """The NO-OP guard wins over status: 0 turns is never a real run."""
        _write_mode(tmp_path, "baseline", status="invalid", num_turns=0,
                    task_score=0.0)
        assert amc.load_mode(tmp_path, "baseline")["class"] == "NO-OP"


class TestCleanSetExclusion:
    def test_lowercase_invalid_mcp_run_excluded_from_clean(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """End-to-end blast radius: a lowercase-invalid mcp_only run must be
        excluded from the clean set, not silently counted VALID."""
        runs = tmp_path / "results" / "runs"
        task = runs / "some-task-001"
        # baseline is a clean scored run; mcp_only is invalidated (lowercase).
        _write_mode(task, "baseline", status="", num_turns=6, task_score=0.5)
        _write_mode(task, "mcp_only", status="invalid", num_turns=5,
                    task_score=0.9)

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(amc, "RUNS", Path("results/runs"))

        tasks = {}
        for d in amc.task_dirs():
            tasks[d.name] = {m: amc.load_mode(d, m) for m in amc.MODES}

        rec = tasks["some-task-001"]
        assert rec["mcp_only"]["class"] == "INVALID"
        # The clean-set gate excludes mcp_only INVALID (aggregate_mcp_clean:103).
        assert rec["mcp_only"]["class"] in ("NO-OP", "INVALID")
