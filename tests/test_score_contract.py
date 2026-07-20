"""Regression suite for the versioned ``task_score`` contract.

The defect this pins: ``test_runner.sh`` emitted a weighted score and
``analyze_scores.py`` divided it by the checkpoint *count* a second time, so a
perfect run on a four-checkpoint task was recorded as 0.25 and cross-task means
were implicitly weighted by 1/checkpoint_count.

Every expected value here is written as a LITERAL. The pre-existing suite
derived its expectations from the same formula it was testing
(``tests/test_analyze_scores.py`` built fixtures via
``task_score / checkpoints_total``), which passes under the buggy and the
corrected implementation alike and is why the defect survived.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from eb_verify.scorer_guard import InfraError, guard_verifier_output
from eb_verify.score_contract import (
    SCORE_CONTRACT_KEY,
    SCORE_CONTRACT_VERSION,
    ScoreContractError,
    read_task_score,
)
from tests.test_shell_runner_integration import _build_workspace, _make_patched_runner

REPO_ROOT = Path(__file__).parent.parent
SCRIPTS = REPO_ROOT / "scripts"
TEST_RUNNER = SCRIPTS / "sandbox" / "test_runner.sh"

for _path in (SCRIPTS, SCRIPTS / "orchestration", SCRIPTS / "infra"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import analyze_scores  # noqa: E402
import cost_tracker  # noqa: E402
import generate_report  # noqa: E402
import run_task  # noqa: E402

# ---------------------------------------------------------------------------
# The contract module itself
# ---------------------------------------------------------------------------


class TestReadTaskScore:
    def test_missing_version_is_refused_by_default(self) -> None:
        with pytest.raises(ScoreContractError, match="predates the score contract"):
            read_task_score({"task_score": 0.8}, "test")

    def test_unknown_future_version_is_refused_even_with_legacy_opt_in(self) -> None:
        """--legacy-score-contract must not become a blanket "read anything"."""
        with pytest.raises(ScoreContractError, match="does not know how to read"):
            read_task_score({SCORE_CONTRACT_KEY: 99}, "test", allow_legacy=True)

    def test_ambiguous_artifact_is_not_sniffed_by_magnitude(self) -> None:
        """A v1 4-checkpoint run at 0.2 each persists 0.8, same as a v2 0.8.

        This is the whole reason the version is mandatory: no heuristic can
        separate these two, so the unversioned one must be refused rather than
        assumed to be the one it resembles. Reading each at its own declared
        contract is what tells them apart, and the two answers differ.
        """
        legacy = {"task_score": 0.8, "checkpoints_total": 4}
        current = {"task_score": 0.8, "checkpoints_total": 4, SCORE_CONTRACT_KEY: 2}

        assert read_task_score(current, "t") == 0.8
        assert read_task_score(legacy, "t", allow_legacy=True) == 0.2


# ---------------------------------------------------------------------------
# Producer: the shell scorer
# ---------------------------------------------------------------------------


def _verifier(score: float) -> str:
    return (
        "#!/bin/bash\n"
        f'echo \'{{"passed": {"true" if score >= 1.0 else "false"}, '
        f'"score": {score}, "detail": "x"}}\'\n'
    )


def _run_scorer(tmp_path: Path, weights: dict[str, float], scores: dict[str, float]):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _build_workspace(
        workspace,
        repos=["repo_a"],
        verifiers={name: _verifier(scores[name]) for name in weights},
        meta={name: f"weight={w}\n" for name, w in weights.items()},
    )
    runner = _make_patched_runner(tmp_path, workspace)
    proc = subprocess.run(
        ["bash", str(runner)], capture_output=True, text=True, timeout=120
    )
    assert proc.stdout.strip(), f"scorer produced nothing:\n{proc.stderr}"
    return json.loads(proc.stdout)


class TestMalformedTaskScore:
    def test_a_null_task_score_is_a_contract_error_not_a_typeerror(self) -> None:
        """`.get(key, default)` does not fire for a present-but-null key.

        The module's whole job is to fail closed with a typed error, so the
        cast belongs to it — a bare TypeError from inside it would be the one
        failure mode it exists to eliminate.
        """
        with pytest.raises(ScoreContractError, match="not a number"):
            read_task_score({"task_score": None, SCORE_CONTRACT_KEY: 2}, "test")

    def test_a_structurally_wrong_task_score_is_a_contract_error(self) -> None:
        """A numeric STRING is not tested here on purpose — float("0.8") is
        0.8, and a producer that quoted its number still said what it scored.
        What has no reading is a value with no numeric meaning at all."""
        with pytest.raises(ScoreContractError, match="not a number"):
            read_task_score(
                {"task_score": [0.8], "checkpoints_total": 4},
                "test",
                allow_legacy=True,
            )


class TestShellProducer:
    def test_shell_constant_matches_python_constant(self) -> None:
        """test_runner.sh is bash and cannot import the contract module.

        The constant is therefore mirrored, like INFRA_SENTINEL and
        NO_VERDICT_REASON already are. This is the test that keeps the mirror
        honest — without it the shell can drift to a version the Python side
        will then refuse, and every run fails at analysis time instead of here.
        """
        source = TEST_RUNNER.read_text()
        match = re.search(r"SCORE_CONTRACT_VERSION=(\d+)", source)
        assert match, "test_runner.sh does not define SCORE_CONTRACT_VERSION"
        assert int(match.group(1)) == SCORE_CONTRACT_VERSION

    def test_production_weight_shape_scores_one_and_carries_the_stamp(
        self, tmp_path: Path
    ) -> None:
        """Deliberately NOT a mean-vs-sum test, and named so.

        These weights sum to 1.0 — the shape task validation enforces, and
        therefore the shape every real task has — which makes the sum and the
        mean the same number. This test cannot detect the defect and is not
        claiming to; it pins the production shape and the version stamp. The
        mean-vs-sum discrimination lives in the two tests below, whose weights
        deliberately do not sum to 1.0.
        """
        result = _run_scorer(
            tmp_path,
            weights={"cp1": 0.5, "cp2": 0.3, "cp3": 0.2},
            scores={"cp1": 1.0, "cp2": 1.0, "cp3": 1.0},
        )
        assert result["task_score"] == pytest.approx(1.0)
        assert result[SCORE_CONTRACT_KEY] == SCORE_CONTRACT_VERSION

    def test_range_holds_even_when_weights_do_not_sum_to_one(
        self, tmp_path: Path
    ) -> None:
        """The invariant is by construction, not by authoring convention.

        Task validation enforces weights summing to 1.0, so this shape cannot
        reach the scorer from a valid task today. That is exactly why it is
        worth testing: the division is the layer that does not depend on the
        validator holding.
        """
        result = _run_scorer(
            tmp_path,
            weights={"cp1": 2.0, "cp2": 2.0},
            scores={"cp1": 1.0, "cp2": 1.0},
        )
        assert result["task_score"] == pytest.approx(1.0)

    def test_a_negative_weight_cannot_push_the_score_above_one(
        self, tmp_path: Path
    ) -> None:
        """A weighted mean stays in [0,1] only while every weight is >= 0.

        Magnitude is harmless — the division cancels it. Sign is not: weights
        2.0 and -1.0 sum to 1.0, pass the positive-total guard, and would
        publish task_score 2.0. Nothing downstream range-checks the top-level
        number (scorer_guard validates per-checkpoint scores, not this one), so
        the parse is where it has to be stopped. A rejected weight falls back
        to the 1.0 default, the same as any other malformed value.
        """
        result = _run_scorer(
            tmp_path,
            weights={"cp1": 2.0, "cp2": -1.0},
            scores={"cp1": 1.0, "cp2": 0.0},
        )
        assert 0.0 <= result["task_score"] <= 1.0

    def test_all_weights_zero_is_an_infra_error_not_a_zero_score(
        self, tmp_path: Path
    ) -> None:
        """Malformed grading metadata must not be recorded as a measured fail.

        Weights are non-negative, so a zero total means every checkpoint was
        weighted zero — a task-authoring defect. Emitting 0.0 would book a
        harness problem as an agent that earned nothing, which is precisely the
        false-zero the scorer trust boundary forbids.
        """
        result = _run_scorer(
            tmp_path,
            weights={"cp1": 0.0, "cp2": 0.0},
            scores={"cp1": 1.0, "cp2": 1.0},
        )
        assert "error" in result
        assert "VERIFIER_INFRA_ERROR" in result["error"]

        guarded = guard_verifier_output(json.dumps(result), 1)
        assert isinstance(guarded, InfraError)

    def test_partial_credit_is_the_weighted_mean_not_the_weighted_sum(
        self, tmp_path: Path
    ) -> None:
        """Weights sum to 2.0, so the mean and the sum diverge.

        The mean is 1.5/2.0 = 0.75; the undivided sum this replaced would
        publish 1.5. Reverting the division in test_runner.sh fails this
        assertion, which the sum-to-1.0 shapes above cannot do.
        """
        result = _run_scorer(
            tmp_path,
            weights={"cp1": 1.5, "cp2": 0.5},
            scores={"cp1": 1.0, "cp2": 0.0},
        )
        assert result["task_score"] == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# Producer: the judge rescore path, which overwrites the shell scorer's number
# ---------------------------------------------------------------------------


class TestJudgeProducer:
    def test_rescore_emits_the_weighted_mean_and_stamps_it(
        self, tmp_path: Path
    ) -> None:
        """_apply_llm_judge is the LAST writer of task_score on a curated task.

        It has to land on the same contract the shell scorer does, so its
        output is exercised on weights that do NOT sum to 1.0 — the shape where
        a weighted sum and a weighted mean disagree. Here the mean is
        (2*1.0 + 2*0.5) / 4 = 0.75; the pre-fix sum published 3.0, a task_score
        three times the maximum the scale allows.
        """
        (tmp_path / "expected_solution.json").write_text(
            json.dumps(
                {
                    "task_id": "t1",
                    "checkpoints": {
                        name: {"expected_solution": "X", "evaluation_criteria": []}
                        for name in ("cp1", "cp2")
                    },
                }
            )
        )
        scores = {
            "task_score": 999.0,  # must be overwritten, not adjusted
            "checkpoints": [
                {"name": "cp1", "score": 1.0, "passed": True, "weight": 2.0},
                {"name": "cp2", "score": 1.0, "passed": True, "weight": 2.0},
            ],
        }
        judge = MagicMock()
        judge.evaluate_checkpoint.side_effect = [
            MagicMock(score=1.0, reasoning=""),
            MagicMock(score=0.5, reasoning=""),
        ]
        agent_output = MagicMock(returncode=0, stdout='{"answer": "X"}', stderr="")

        with patch.object(run_task, "_docker_exec", return_value=agent_output), patch(
            "eb_verify.judge.LLMJudge", return_value=judge
        ):
            out = run_task._apply_llm_judge(scores, tmp_path, "cid", {})

        assert "verifier_infra_error" not in out
        assert out["task_score"] == pytest.approx(0.75)
        assert out[SCORE_CONTRACT_KEY] == SCORE_CONTRACT_VERSION


# ---------------------------------------------------------------------------
# Consumer: analysis, across materially different task shapes
# ---------------------------------------------------------------------------


def _write_result(
    directory: Path,
    task_id: str,
    *,
    task_score: float,
    n_checkpoints: int,
    contract_version: int | None = SCORE_CONTRACT_VERSION,
    mode: str = "baseline",
    all_passed: bool = True,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    scores: dict = {
        "task_score": task_score,
        "all_passed": all_passed,
        "checkpoints_passed": n_checkpoints if all_passed else 0,
        "checkpoints_total": n_checkpoints,
        "checkpoints": [
            {
                "name": f"cp{i}",
                "weight": round(1.0 / n_checkpoints, 4),
                "score": task_score,
                "passed": all_passed,
            }
            for i in range(n_checkpoints)
        ],
    }
    if contract_version is not None:
        scores[SCORE_CONTRACT_KEY] = contract_version

    path = directory / "results.json"
    path.write_text(
        json.dumps(
            {
                "task_id": task_id,
                "success": True,
                "phase": "complete",
                "scores": scores,
                "task_metadata": {
                    "suite": "platform_engineering",
                    "task_type": "config_drift",
                    "difficulty": "medium",
                    "languages": ["python"],
                },
                "config": {"mode": mode},
            }
        )
    )
    return path


class TestAnalysisConsumesWeightedScoreDirectly:
    def test_equal_weighted_outcomes_are_equal_across_task_shapes(
        self, tmp_path: Path
    ) -> None:
        """The headline regression.

        Four tasks, 2 / 3 / 4 / 5 checkpoints, each scoring a perfect weighted
        1.0. Before the fix analysis recorded 0.5 / 0.3333 / 0.25 / 0.2 — the
        same outcome ranked four different ways, and every cross-task mean
        implicitly weighted by 1/checkpoint_count.
        """
        shapes = {"t-2cp": 2, "t-3cp": 3, "t-4cp": 4, "t-5cp": 5}
        for task_id, n in shapes.items():
            _write_result(tmp_path / task_id, task_id, task_score=1.0, n_checkpoints=n)

        results = [
            analyze_scores.parse_result(p, REPO_ROOT / "benchmarks")
            for p in sorted(tmp_path.rglob("results.json"))
        ]
        assert len(results) == 4
        assert [r.normalized_score for r in results] == [1.0, 1.0, 1.0, 1.0]

    def test_partial_credit_survives_analysis_unchanged(self, tmp_path: Path) -> None:
        _write_result(
            tmp_path / "t", "t", task_score=0.6, n_checkpoints=4, all_passed=False
        )
        r = analyze_scores.parse_result(
            tmp_path / "t" / "results.json", REPO_ROOT / "benchmarks"
        )
        assert r is not None
        assert r.normalized_score == 0.6  # not 0.15

    def test_unversioned_result_is_refused_not_reinterpreted(
        self, tmp_path: Path
    ) -> None:
        _write_result(
            tmp_path / "t", "t", task_score=0.8, n_checkpoints=4, contract_version=None
        )
        with pytest.raises(ScoreContractError):
            analyze_scores.parse_result(
                tmp_path / "t" / "results.json", REPO_ROOT / "benchmarks"
            )

    def test_legacy_opt_in_quantifies_the_corrected_versus_legacy_change(
        self, tmp_path: Path
    ) -> None:
        """Locked legacy fixture: the same bytes, read both ways.

        A v1 four-checkpoint artifact at task_score 4.0 (the unweighted 0-N sum
        a perfect pre-contract run produced) reads as 1.0 under v1 semantics.
        The same artifact stamped v2 reads as 4.0 — out of range, which is the
        signal that the stamp and the bytes disagree, not a number to average.
        """
        _write_result(
            tmp_path / "t", "t", task_score=4.0, n_checkpoints=4, contract_version=None
        )
        path = tmp_path / "t" / "results.json"

        legacy = analyze_scores.parse_result(
            path, REPO_ROOT / "benchmarks", allow_legacy=True
        )
        assert legacy is not None
        assert legacy.normalized_score == 1.0
        assert legacy.task_score == 4.0

    def test_infra_error_artifact_is_skipped_not_raised_on(
        self, tmp_path: Path
    ) -> None:
        """The integrity/infra channel must survive a fail-closed contract.

        run_task.py synthesizes {"task_score": 0.0, "all_passed": false} with no
        checkpoints for a tampered seal or a verifier infra error, and
        chain_runner writes {"scores": {"task_score": ...}} alone. None carries
        a contract stamp. They are dropped by the zero-checkpoint filter, which
        must therefore run BEFORE the version check — otherwise fail-closed
        turns the infra channel into a crash.
        """
        d = tmp_path / "t"
        d.mkdir()
        (d / "results.json").write_text(
            json.dumps(
                {
                    "task_id": "t",
                    "success": False,
                    "scores": {
                        "task_score": 0.0,
                        "all_passed": False,
                        "verifier_infra_error": {"reason": "empty_verifier_output"},
                    },
                }
            )
        )
        assert (
            analyze_scores.parse_result(d / "results.json", REPO_ROOT / "benchmarks")
            is None
        )


# ---------------------------------------------------------------------------
# Aggregation and reporting: the same equality has to survive both
# ---------------------------------------------------------------------------


class TestAggregationAcrossShapes:
    def test_calibration_bias_threshold_is_now_a_reward_fraction(
        self, tmp_path: Path
    ) -> None:
        """The threshold's scale changed, and that is deliberate.

        bias_threshold=0.10 was applied to means of task_score/N, a quantity
        with no nameable unit. On the corrected scale it is what its name says:
        a 10-percentage-point difference in mean reward between modes. This
        pins the consequence — a corpus whose modes differ by 0.2 of the
        available reward IS flagged, where the legacy scale would have shrunk
        the same difference to 0.0667 on 3-checkpoint tasks and passed it.
        """
        _write_result(
            tmp_path / "cal-1-baseline", "cal-001", task_score=1.0, n_checkpoints=3
        )
        _write_result(
            tmp_path / "cal-1-mcp",
            "cal-001",
            task_score=0.8,
            n_checkpoints=3,
            mode="mcp_only",
        )
        results = [
            analyze_scores.parse_result(p, REPO_ROOT / "benchmarks")
            for p in sorted(tmp_path.rglob("results.json"))
        ]
        bias = analyze_scores.calibration_bias([r for r in results if r])

        assert bias["max_mode_delta"] == pytest.approx(0.2)
        assert bias["bias_flagged"] is True
        assert round(0.2 / 3, 4) < bias["bias_threshold"]  # what v1 would have seen

    def test_two_shapes_that_scored_the_same_read_the_same_in_the_report(
        self, tmp_path: Path
    ) -> None:
        """The last leg: scorer output -> results.json -> analysis -> report.

        A 2-checkpoint and a 5-checkpoint task, both perfect. Because N differs
        per task, the old mean was mean(task_score / N_task), so many-checkpoint
        tasks contributed less to every mean, median and delta — this corpus
        printed 0.35 for a run in which every task scored perfectly. The
        aggregate and the rendered report must now both show 1.000.
        """
        _write_result(tmp_path / "a", "a", task_score=1.0, n_checkpoints=2)
        _write_result(tmp_path / "b", "b", task_score=1.0, n_checkpoints=5)

        analysis = analyze_scores.analyze([tmp_path], REPO_ROOT / "benchmarks")
        assert analysis["by_mode"]["baseline"]["mean"] == 1.0

        inputs = generate_report.ReportInputs(
            score_analysis=analysis,
            cost_report=None,
            reproducibility_report=None,
            charts_dir=None,
            available_charts=frozenset(),
        )
        section = generate_report.build_score_by_mode(inputs)
        assert "1.000" in section
        assert "0.350" not in section

    def test_analysis_declares_the_contract_it_was_read_at(
        self, tmp_path: Path
    ) -> None:
        _write_result(tmp_path / "a", "a", task_score=1.0, n_checkpoints=3)
        analysis = analyze_scores.analyze([tmp_path], REPO_ROOT / "benchmarks")
        assert analysis["score_contract_version"] == SCORE_CONTRACT_VERSION


# ---------------------------------------------------------------------------
# Cost selection: the one place the fix can reorder a published number
# ---------------------------------------------------------------------------


class TestCostAttemptSelection:
    def test_selection_changes_when_a_cell_has_attempts_of_different_shapes(
        self, tmp_path: Path
    ) -> None:
        """Pinned as a known behaviour change, not asserted to be inert.

        checkpoints_total is a count of .verifiers/*.sh present in that
        container, so a task whose checkpoint set changed between batches has
        attempts of the same (task_id, mode) cell with different N — and
        cost_tracker scans across batches by design. Under the old division,
        attempt B (0.4 over 1 checkpoint -> 0.4) beat attempt A (0.5 over 2 ->
        0.25). Under the contract, A's higher weighted score wins, which is the
        answer the scorer actually produced.

        The pre-existing cost fixtures all hardcode checkpoints_total=1, so the
        old suite could not see this either way.
        """
        a = _write_result(
            tmp_path / "batch1" / "t", "t", task_score=0.5, n_checkpoints=2
        )
        b = _write_result(
            tmp_path / "batch2" / "t", "t", task_score=0.4, n_checkpoints=1
        )

        score_a = cost_tracker._attempt_score(a.parent, REPO_ROOT / "benchmarks")
        score_b = cost_tracker._attempt_score(b.parent, REPO_ROOT / "benchmarks")

        assert score_a == 0.5
        assert score_b == 0.4
        assert score_a > score_b  # legacy: 0.25 < 0.4, so B was published
