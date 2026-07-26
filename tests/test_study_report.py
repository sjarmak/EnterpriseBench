"""Contract tests for the capsule-driven study report.

The promotion path's failure mode was not a wrong number, it was an unprovable
one: an artifact promoted under a run ID that had absorbed scores from
unrelated trees. These tests pin the boundary — the report reads receipts of
the named study or it produces nothing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from analysis.study_report import build_report, main  # noqa: E402
from eb_study import StudyCapsule  # noqa: E402

from tests.test_study_capsule import (  # noqa: E402
    full_receipts,
    make_receipt,
    make_spec,
)


def capsule(spec=None, receipts=None) -> StudyCapsule:
    spec = spec or make_spec()
    return StudyCapsule.build(spec, receipts if receipts is not None else full_receipts(spec))


class TestProvenance:
    def test_report_names_everything_the_study_froze(self):
        report = build_report(capsule())
        prov = report["provenance"]
        assert prov["study_id"] == "rryas-headline-2026-07"
        assert prov["model"] == "claude-opus-4-8"
        assert prov["revision"] == "e439534"
        assert prov["score_contract"] == "weighted-mean-v2"
        assert prov["attempt_policy"] == "all_valid_repetitions"
        assert prov["token_source"] == "sdk_model_usage"
        assert prov["spec_hash"].startswith("sha256:")

    def test_completeness_names_the_excluded_tasks(self):
        spec = make_spec()
        receipts = [
            r
            for r in full_receipts(spec)
            if not (r.trial.task_id == "dep-traversal-002" and r.trial.repetition == 2)
        ]
        comp = build_report(capsule(spec, receipts))["completeness"]
        assert comp["declared_tasks"] == 2
        assert comp["paired_tasks"] == 1
        assert comp["excluded_tasks"] == {
            "dep-traversal-002": ["baseline/rep2", "mcp_only/rep2", "cli/rep2"]
        }


class TestReward:
    def test_every_declared_arm_gets_a_contrast(self):
        """A third arm that executes correctly must appear in the deltas."""

        contrasts = build_report(capsule())["reward"]["contrasts"]
        assert sorted(contrasts) == ["cli_vs_baseline", "mcp_only_vs_baseline"]

    def test_contrast_is_paired_over_the_matched_task_set(self):
        spec = make_spec()
        receipts = [
            r
            for r in full_receipts(spec)
            if not (r.trial.task_id == "dep-traversal-001" and r.trial.arm == "cli")
        ]
        receipts += [
            make_receipt(spec, "dep-traversal-001", "cli", rep, score=0.9) for rep in (1, 2)
        ]
        contrast = build_report(capsule(spec, receipts))["reward"]["contrasts"]["cli_vs_baseline"]
        assert contrast["n_paired"] == 2
        assert contrast["mean_delta"] == pytest.approx(0.2)
        assert contrast["pct_improved"] == 0.5

    def test_scores_are_not_renormalized_by_checkpoint_count(self):
        """A perfect trial reports 1.0, not 1.0 divided by anything."""

        spec = make_spec()
        receipts = [
            make_receipt(spec, task_id, arm, rep, score=1.0)
            for task_id in spec.task_ids
            for arm in spec.arm_names
            for rep in (1, 2)
        ]
        by_arm = build_report(capsule(spec, receipts))["reward"]["by_arm"]
        assert all(stats["mean"] == 1.0 for stats in by_arm.values())


class TestEconomics:
    def test_the_two_views_are_reported_separately(self):
        spec = make_spec()
        receipts = full_receipts(spec)
        receipts.append(
            make_receipt(
                spec,
                "dep-traversal-001",
                "cli",
                1,
                status="infra_invalid",
                failure_class="repo_clone_failed",
                score=None,
                trial={"attempt": 2},
            )
        )
        econ = build_report(capsule(spec, receipts))["economics"]
        assert econ["paired_valid"]["total_cost_usd"] == pytest.approx(15.0)
        assert econ["all_attempts"]["total_cost_usd"] == pytest.approx(16.25)
        assert econ["paired_valid"]["by_arm_usd"]["cli"] == pytest.approx(5.0)
        assert econ["all_attempts"]["by_arm_usd"]["cli"] == pytest.approx(6.25)

    def test_no_blended_total_is_published(self):
        econ = build_report(capsule())["economics"]
        assert set(econ) == {"paired_valid", "all_attempts"}


class TestCli:
    def _write(self, tmp_path, spec, receipts):
        spec_path = tmp_path / "study.json"
        spec_path.write_text(json.dumps(spec.to_json()))
        receipts_path = tmp_path / "receipts.jsonl"
        receipts_path.write_text(
            "".join(json.dumps(r.to_json(), sort_keys=True) + "\n" for r in receipts)
        )
        return spec_path, receipts_path

    def test_writes_a_report_for_a_complete_study(self, tmp_path):
        spec = make_spec()
        spec_path, receipts_path = self._write(tmp_path, spec, full_receipts(spec))
        out = tmp_path / "report.json"
        assert main(["--spec", str(spec_path), "--receipts", str(receipts_path), "--output", str(out)]) == 0
        assert json.loads(out.read_text())["completeness"]["paired_tasks"] == 2

    def test_a_missing_arm_fails_closed_and_writes_nothing(self, tmp_path):
        spec = make_spec()
        receipts = [r for r in full_receipts(spec) if r.trial.arm != "cli"]
        spec_path, receipts_path = self._write(tmp_path, spec, receipts)
        out = tmp_path / "report.json"
        assert main(["--spec", str(spec_path), "--receipts", str(receipts_path), "--output", str(out)]) == 2
        assert not out.exists()

    def test_a_foreign_receipt_fails_closed(self, tmp_path):
        """The historical failure: unrelated runs joining the promoted artifact."""

        spec = make_spec()
        foreign = make_receipt(make_spec(study_id="smoke-run"), "dep-traversal-001", "cli", 1)
        spec_path, receipts_path = self._write(tmp_path, spec, full_receipts(spec) + [foreign])
        out = tmp_path / "report.json"
        assert main(["--spec", str(spec_path), "--receipts", str(receipts_path), "--output", str(out)]) == 2
        assert not out.exists()
