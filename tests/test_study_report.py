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

import analysis.study_report as study_report_module  # noqa: E402
from analysis.study_inference import AnalysisContract  # noqa: E402
from analysis.study_report import build_report, main  # noqa: E402
from eb_study import (  # noqa: E402
    CapsuleError,
    StudyCapsule,
    StudySpec,
    file_hash,
)

from tests.test_study_capsule import (  # noqa: E402
    full_receipts,
    make_receipt,
    make_spec,
)
from tests.test_study_inference import _write_contract_files  # noqa: E402


def capsule(spec=None, receipts=None) -> StudyCapsule:
    spec = spec or make_spec()
    return StudyCapsule.build(
        spec, receipts if receipts is not None else full_receipts(spec)
    )


def analysis_contract(spec) -> AnalysisContract:
    task_types = {
        task_id: ("dependency_graph" if index == 0 else "error_provenance")
        for index, task_id in enumerate(spec.task_ids)
    }
    return AnalysisContract(
        plan_hash="sha256:plan",
        manifest_hash=spec.task_manifest_hash,
        confidence_level=0.95,
        bootstrap_repetitions=10_000,
        bootstrap_seed=20_260_728,
        parity_margin=0.05,
        primary_contrasts=(
            ("mcp_only", "baseline"),
            ("cli", "baseline"),
        ),
        descriptive_contrast=("cli", "mcp_only"),
        descriptive_reason="interface and source availability both change",
        task_types=task_types,
    )


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

    def test_supplemental_source_hashes_cannot_override_frozen_provenance(self):
        with pytest.raises(CapsuleError, match="source hashes"):
            build_report(
                capsule(),
                source_hashes={
                    "study_spec_file_hash": "sha256:" + ("a" * 64),
                    "receipts_file_hash": "sha256:" + ("b" * 64),
                    "study_id": "forged-study",
                },
            )

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

    def test_report_binds_every_paired_measurement_to_its_trial_key(self):
        report = build_report(capsule())

        assert report["reward"]["trace_evidence"]["dep-traversal-001"]["baseline"] == [
            ("rryas-headline-2026-07/dep-traversal-001/baseline/rep1/att1"),
            ("rryas-headline-2026-07/dep-traversal-001/baseline/rep2/att1"),
        ]


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
            make_receipt(spec, "dep-traversal-001", "cli", rep, score=0.9)
            for rep in (1, 2)
        ]
        contrast = build_report(capsule(spec, receipts))["reward"]["contrasts"][
            "cli_vs_baseline"
        ]
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

    def test_locked_complete_analysis_replaces_legacy_significance_fields(self):
        spec = make_spec(repetitions=1, max_attempts=1)
        report = build_report(
            capsule(spec, full_receipts(spec)),
            contract=analysis_contract(spec),
        )

        assert report["schema_version"] == 3
        assert report["analysis"]["status"] == "complete"
        assert report["completeness"]["headline_eligible"] is True
        assert report["provenance"]["analysis_plan_hash"] == "sha256:plan"
        assert report["provenance"]["task_manifest_hash"] == spec.task_manifest_hash
        assert set(report["reward"]["primary_contrasts"]) == {
            "mcp_only_vs_baseline",
            "cli_vs_baseline",
        }
        assert report["reward"]["method"]["bootstrap_repetitions"] == 10_000
        assert report["reward"]["by_task_type"]["dependency_graph"]["n_tasks"] == 1
        assert "wilcoxon_p" not in json.dumps(report["reward"])
        assert "significant" not in json.dumps(report["reward"])

    def test_incomplete_locked_analysis_withholds_every_reward_result(self):
        spec = make_spec(repetitions=1, max_attempts=1)
        receipts = [
            receipt
            for receipt in full_receipts(spec)
            if not (
                receipt.trial.task_id == "dep-traversal-002"
                and receipt.trial.arm == "cli"
            )
        ]

        report = build_report(
            capsule(spec, receipts),
            contract=analysis_contract(spec),
        )

        assert report["analysis"]["status"] == "withheld_incomplete"
        assert report["completeness"]["headline_eligible"] is False
        assert report["completeness"]["valid_slots"] == 5
        assert report["completeness"]["missing_or_invalid_slots"] == [
            "dep-traversal-002/cli/rep1"
        ]
        assert report["reward"] is None
        assert report["economics"]["all_attempts"]["receipts"] == 5

    def test_zero_complete_pairs_still_emit_withheld_schema_v3(self):
        spec = make_spec(repetitions=1, max_attempts=1)

        report = build_report(
            capsule(
                spec,
                [
                    make_receipt(spec, task_id, "baseline", 1)
                    for task_id in spec.task_ids
                ],
            ),
            contract=analysis_contract(spec),
        )

        assert report["schema_version"] == 3
        assert report["analysis"]["status"] == "withheld_incomplete"
        assert report["reward"] is None
        assert report["completeness"]["paired_tasks"] == 0
        assert report["completeness"]["valid_slots"] == len(spec.task_ids)
        assert set(report["completeness"]["excluded_tasks"]) == set(spec.task_ids)
        assert report["economics"]["paired_valid"]["trials"] == 0


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
        assert econ["paired_valid"]["per_task_usd"]["dep-traversal-001"] == {
            "baseline": 2.5,
            "cli": 2.5,
            "mcp_only": 2.5,
        }

    def test_no_blended_total_is_published(self):
        econ = build_report(capsule())["economics"]
        assert set(econ) == {"paired_valid", "all_attempts"}

    def test_missing_provider_cost_is_disclosed_instead_of_counted_as_zero(self):
        spec = make_spec()
        receipts = full_receipts(spec)
        target = next(
            receipt
            for receipt in receipts
            if receipt.trial.task_id == "dep-traversal-001"
            and receipt.trial.arm == "cli"
            and receipt.trial.repetition == 1
        )
        receipts[receipts.index(target)] = make_receipt(
            spec,
            target.trial.task_id,
            target.trial.arm,
            target.trial.repetition,
            usage={
                "source": "sdk_model_usage",
                "cost_usd": None,
                "model_usage": {
                    "gpt-5.6-sol": {
                        "input_tokens": 10,
                        "output_tokens": 20,
                        "cost_usd": None,
                    }
                },
            },
        )

        econ = build_report(capsule(spec, receipts))["economics"]

        assert econ["paired_valid"]["total_cost_usd"] is None
        assert econ["paired_valid"]["by_arm_usd"]["cli"] is None
        assert econ["paired_valid"]["cost_coverage"] == {
            "costed_trials": 11,
            "missing_cost_trials": 1,
        }

    def test_overflowing_aggregate_cost_fails_closed(self):
        spec = make_spec()
        receipts = [
            make_receipt(
                spec,
                task_id,
                arm,
                rep,
                usage={
                    "source": "sdk_model_usage",
                    "cost_usd": 1e308,
                    "model_usage": {
                        "claude-opus-4-8": {
                            "input_tokens": 1,
                            "output_tokens": 1,
                        }
                    },
                },
            )
            for task_id in spec.task_ids
            for arm in spec.arm_names
            for rep in (1, 2)
        ]

        with pytest.raises(CapsuleError, match="aggregate cost must be finite"):
            build_report(capsule(spec, receipts))


class TestTokens:
    @staticmethod
    def _usage() -> dict:
        return {
            "source": "sdk_model_usage",
            "cost_usd": 0.3,
            "model_usage": {
                "claude-opus-4-8": {
                    "input_tokens": 10,
                    "output_tokens": 2,
                    "cache_write_tokens": 3,
                    "cache_read_tokens": 5,
                    "cost_usd": 0.1,
                },
                "claude-haiku-4-5": {
                    "input_tokens": 1,
                    "output_tokens": 4,
                    "cache_write_tokens": 6,
                    "cache_read_tokens": 7,
                    "cost_usd": 0.2,
                },
            },
        }

    def test_reports_every_sdk_token_category_and_model(self):
        spec = make_spec()
        receipts = [
            make_receipt(
                spec,
                task_id,
                arm,
                rep,
                usage=self._usage(),
            )
            for task_id in spec.task_ids
            for arm in spec.arm_names
            for rep in (1, 2)
        ]

        tokens = build_report(capsule(spec, receipts))["tokens"]["paired_valid"]

        assert tokens["definition"] == (
            "combined_tokens = input + output + cache_creation + cache_read "
            "across every SDK-reported model"
        )
        assert tokens["coverage"] == {
            "tokenized_receipts": 12,
            "missing_usage_receipts": 0,
        }
        assert tokens["total"] == {
            "input_tokens": 132,
            "output_tokens": 72,
            "cache_creation_tokens": 108,
            "cache_read_tokens": 144,
            "combined_tokens": 456,
        }
        assert tokens["by_arm"]["cli"]["combined_tokens"] == 152
        assert tokens["by_model"]["claude-opus-4-8"]["combined_tokens"] == 240
        assert tokens["by_model"]["claude-haiku-4-5"]["combined_tokens"] == 216
        assert tokens["per_task"]["dep-traversal-001"]["cli"]["combined_tokens"] == 76

    def test_missing_usage_is_disclosed_instead_of_counted_as_zero(self):
        spec = make_spec()
        receipts = [
            make_receipt(
                spec,
                task_id,
                arm,
                rep,
                usage=self._usage(),
            )
            for task_id in spec.task_ids
            for arm in spec.arm_names
            for rep in (1, 2)
        ]
        receipts.append(
            make_receipt(
                spec,
                "dep-traversal-001",
                "cli",
                1,
                status="infra_invalid",
                failure_class="provider_usage_missing",
                score=None,
                usage=None,
                trial={"attempt": 2},
            )
        )

        tokens = build_report(capsule(spec, receipts))["tokens"]

        assert tokens["paired_valid"]["total"]["combined_tokens"] == 456
        assert tokens["all_attempts"]["total"] is None
        assert tokens["all_attempts"]["by_arm"]["cli"] is None
        assert tokens["all_attempts"]["coverage"] == {
            "tokenized_receipts": 12,
            "missing_usage_receipts": 1,
        }

    def test_legacy_sdk_field_names_are_normalized(self):
        report = build_report(capsule())

        assert report["tokens"]["paired_valid"]["total"] == {
            "input_tokens": 120,
            "output_tokens": 240,
            "cache_creation_tokens": 0,
            "cache_read_tokens": 0,
            "combined_tokens": 360,
        }

    def test_vendor_qualified_model_identifier_is_preserved(self):
        spec = make_spec()
        receipts = full_receipts(spec)
        target = receipts[0]
        model = "openrouter:moonshotai/kimi-k2.5+preview@2026"
        receipts[0] = make_receipt(
            spec,
            target.trial.task_id,
            target.trial.arm,
            target.trial.repetition,
            usage={
                "source": "sdk_model_usage",
                "cost_usd": 0.1,
                "model_usage": {
                    model: {
                        "input_tokens": 1,
                        "output_tokens": 1,
                    }
                },
            },
        )

        by_model = build_report(capsule(spec, receipts))["tokens"]["paired_valid"][
            "by_model"
        ]

        assert by_model[model]["combined_tokens"] == 2

    @pytest.mark.parametrize(
        ("model_usage", "message"),
        (
            (
                {
                    "input_tokens": 1,
                    "inputTokens": 2,
                    "output_tokens": 3,
                },
                "conflicting input_tokens/inputTokens",
            ),
            (
                {"output_tokens": 3},
                "missing input_tokens",
            ),
            (
                {"input_tokens": 1, "output_tokens": -1},
                "must be a non-negative integer",
            ),
            (
                {"input_tokens": [], "output_tokens": 1},
                "must be a non-negative integer",
            ),
            (
                {"input_tokens": 2**63, "output_tokens": 1},
                "signed 64-bit",
            ),
        ),
    )
    def test_malformed_sdk_token_usage_fails_closed(self, model_usage, message):
        spec = make_spec()
        receipts = full_receipts(spec)
        target = receipts[0]
        receipts[0] = make_receipt(
            spec,
            target.trial.task_id,
            target.trial.arm,
            target.trial.repetition,
            usage={
                "source": "sdk_model_usage",
                "cost_usd": 0.1,
                "model_usage": {"claude-opus-4-8": model_usage},
            },
        )

        with pytest.raises(CapsuleError, match=message):
            build_report(capsule(spec, receipts))

    def test_per_model_combined_token_overflow_fails_closed(self):
        spec = make_spec()
        receipts = full_receipts(spec)
        target = receipts[0]
        receipts[0] = make_receipt(
            spec,
            target.trial.task_id,
            target.trial.arm,
            target.trial.repetition,
            usage={
                "source": "sdk_model_usage",
                "cost_usd": 0.1,
                "model_usage": {
                    "claude-opus-4-8": {
                        "input_tokens": 2**63 - 1,
                        "output_tokens": 1,
                    }
                },
            },
        )

        with pytest.raises(CapsuleError, match="aggregate token count"):
            build_report(capsule(spec, receipts))

    def test_cross_model_token_overflow_fails_closed(self):
        spec = make_spec()
        receipts = full_receipts(spec)
        target = receipts[0]
        half_plus_one = 2**62
        receipts[0] = make_receipt(
            spec,
            target.trial.task_id,
            target.trial.arm,
            target.trial.repetition,
            usage={
                "source": "sdk_model_usage",
                "cost_usd": 0.1,
                "model_usage": {
                    "claude-opus-4-8": {
                        "input_tokens": half_plus_one,
                        "output_tokens": 0,
                    },
                    "claude-haiku-4-5": {
                        "input_tokens": half_plus_one,
                        "output_tokens": 0,
                    },
                },
            },
        )

        with pytest.raises(CapsuleError, match="aggregate token count"):
            build_report(capsule(spec, receipts))

    def test_cross_receipt_token_overflow_fails_closed(self):
        spec = make_spec()
        receipts = full_receipts(spec)
        first, second = receipts[:2]
        receipts[0] = make_receipt(
            spec,
            first.trial.task_id,
            first.trial.arm,
            first.trial.repetition,
            usage={
                "source": "sdk_model_usage",
                "cost_usd": 0.1,
                "model_usage": {
                    "claude-opus-4-8": {
                        "input_tokens": 2**63 - 1,
                        "output_tokens": 0,
                    }
                },
            },
        )
        receipts[1] = make_receipt(
            spec,
            second.trial.task_id,
            second.trial.arm,
            second.trial.repetition,
            usage={
                "source": "sdk_model_usage",
                "cost_usd": 0.1,
                "model_usage": {
                    "claude-opus-4-8": {
                        "input_tokens": 1,
                        "output_tokens": 0,
                    }
                },
            },
        )

        with pytest.raises(CapsuleError, match="aggregate token count"):
            build_report(capsule(spec, receipts))


class TestTiming:
    def test_reports_paired_and_all_attempt_wall_time(self):
        report = build_report(capsule())
        timing = report["timing"]["paired_valid"]

        assert timing["total_elapsed_seconds"] == 7200.0
        assert timing["by_arm"]["baseline"] == {
            "trials": 4,
            "total_elapsed_seconds": 2400.0,
            "mean_elapsed_seconds": 600.0,
        }
        assert timing["per_task_seconds"]["dep-traversal-001"]["cli"] == 1200.0

    @pytest.mark.parametrize(
        ("started_at", "ended_at", "message"),
        (
            ("not-a-time", "2026-07-20T00:10:00Z", "invalid started_at"),
            (
                "2026-07-20T00:10:00Z",
                "2026-07-20T00:00:00Z",
                "ended before it started",
            ),
            (
                "2026-07-20T00:00:00",
                "2026-07-20T00:10:00",
                "timezone-aware",
            ),
        ),
    )
    def test_malformed_wall_time_fails_closed(self, started_at, ended_at, message):
        spec = make_spec()
        receipts = full_receipts(spec)
        target = receipts[0]
        receipts[0] = make_receipt(
            spec,
            target.trial.task_id,
            target.trial.arm,
            target.trial.repetition,
            started_at=started_at,
            ended_at=ended_at,
        )

        with pytest.raises(CapsuleError, match=message):
            build_report(capsule(spec, receipts))


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
        assert (
            main(
                [
                    "--spec",
                    str(spec_path),
                    "--receipts",
                    str(receipts_path),
                    "--output",
                    str(out),
                ]
            )
            == 0
        )
        assert json.loads(out.read_text())["completeness"]["paired_tasks"] == 2

    def test_writes_locked_analysis_only_from_both_bound_inputs(self, tmp_path):
        provisional = make_spec(repetitions=1, max_attempts=1)
        plan_path, manifest_path = _write_contract_files(tmp_path, provisional)
        payload = provisional.to_json()
        payload["task_manifest_hash"] = file_hash(manifest_path)
        spec = StudySpec.from_json(payload)
        spec_path, receipts_path = self._write(
            tmp_path,
            spec,
            full_receipts(spec),
        )
        out = tmp_path / "locked-report.json"

        assert (
            main(
                [
                    "--spec",
                    str(spec_path),
                    "--receipts",
                    str(receipts_path),
                    "--analysis-plan",
                    str(plan_path),
                    "--task-manifest",
                    str(manifest_path),
                    "--output",
                    str(out),
                ]
            )
            == 0
        )
        report = json.loads(out.read_text())
        assert report["analysis"]["status"] == "complete"
        assert report["provenance"]["analysis_plan_hash"] == file_hash(plan_path)
        assert report["provenance"]["task_manifest_hash"] == (file_hash(manifest_path))

    def test_repository_v6_partial_report_binds_every_frozen_source(
        self,
        tmp_path,
    ):
        study_dir = PROJECT_ROOT / "configs" / "studies" / "rryas-headline-v6"
        receipts_path = (
            PROJECT_ROOT
            / "results"
            / "studies"
            / "rryas-headline-v6"
            / "receipts.jsonl"
        )
        spec_path = study_dir / "study_spec.json"
        plan_path = study_dir / "analysis_plan.json"
        manifest_path = study_dir / "final_manifest.json"
        out = tmp_path / "report.json"

        assert (
            main(
                [
                    "--spec",
                    str(spec_path),
                    "--receipts",
                    str(receipts_path),
                    "--analysis-plan",
                    str(plan_path),
                    "--task-manifest",
                    str(manifest_path),
                    "--output",
                    str(out),
                ]
            )
            == 0
        )
        report = json.loads(out.read_text())
        provenance = report["provenance"]
        assert provenance["study_spec_file_hash"] == file_hash(spec_path)
        assert provenance["receipts_file_hash"] == file_hash(receipts_path)
        assert provenance["candidate_manifest_hash"].startswith("sha256:")
        assert provenance["execution_order_hash"].startswith("sha256:")
        assert provenance["execution_order_count"] == 90
        assert provenance["agent_account"] == 3
        assert provenance["judge_account"] == 1
        assert provenance["task_type_counts"] == {
            "dependency_graph": 13,
            "error_provenance": 3,
            "incident_investigation": 14,
        }
        assert report["analysis"]["status"] == "withheld_incomplete"
        assert report["reward"] is None

    @pytest.mark.parametrize("provided", ("analysis-plan", "task-manifest"))
    def test_one_locked_input_without_the_other_fails_before_output(
        self,
        tmp_path,
        provided,
    ):
        spec = make_spec()
        spec_path, receipts_path = self._write(tmp_path, spec, full_receipts(spec))
        extra = tmp_path / f"{provided}.json"
        extra.write_text("{}")
        out = tmp_path / "report.json"

        assert (
            main(
                [
                    "--spec",
                    str(spec_path),
                    "--receipts",
                    str(receipts_path),
                    f"--{provided}",
                    str(extra),
                    "--output",
                    str(out),
                ]
            )
            == 2
        )
        assert not out.exists()

    def test_writes_a_report_when_provider_cost_is_unavailable(self, tmp_path, capsys):
        spec = make_spec()
        receipts = full_receipts(spec)
        target = receipts[0]
        receipts[0] = make_receipt(
            spec,
            target.trial.task_id,
            target.trial.arm,
            target.trial.repetition,
            usage={
                "source": "sdk_model_usage",
                "cost_usd": None,
                "model_usage": {
                    spec.model: {
                        "input_tokens": 10,
                        "output_tokens": 20,
                        "cost_usd": None,
                    }
                },
            },
        )
        spec_path, receipts_path = self._write(tmp_path, spec, receipts)
        out = tmp_path / "report.json"

        assert (
            main(
                [
                    "--spec",
                    str(spec_path),
                    "--receipts",
                    str(receipts_path),
                    "--output",
                    str(out),
                ]
            )
            == 0
        )
        assert (
            json.loads(out.read_text())["economics"]["paired_valid"]["total_cost_usd"]
            is None
        )
        assert "paired-valid unavailable" in capsys.readouterr().err

    def test_a_missing_arm_fails_closed_and_writes_nothing(self, tmp_path):
        spec = make_spec()
        receipts = [r for r in full_receipts(spec) if r.trial.arm != "cli"]
        spec_path, receipts_path = self._write(tmp_path, spec, receipts)
        out = tmp_path / "report.json"
        assert (
            main(
                [
                    "--spec",
                    str(spec_path),
                    "--receipts",
                    str(receipts_path),
                    "--output",
                    str(out),
                ]
            )
            == 2
        )
        assert not out.exists()

    def test_a_foreign_receipt_fails_closed(self, tmp_path):
        """The historical failure: unrelated runs joining the promoted artifact."""

        spec = make_spec()
        foreign = make_receipt(
            make_spec(study_id="smoke-run"), "dep-traversal-001", "cli", 1
        )
        spec_path, receipts_path = self._write(
            tmp_path, spec, full_receipts(spec) + [foreign]
        )
        out = tmp_path / "report.json"
        assert (
            main(
                [
                    "--spec",
                    str(spec_path),
                    "--receipts",
                    str(receipts_path),
                    "--output",
                    str(out),
                ]
            )
            == 2
        )
        assert not out.exists()

    def test_malformed_usage_fails_before_writing_output(self, tmp_path):
        spec = make_spec()
        receipts = full_receipts(spec)
        target = receipts[0]
        receipts[0] = make_receipt(
            spec,
            target.trial.task_id,
            target.trial.arm,
            target.trial.repetition,
            usage={
                "source": "sdk_model_usage",
                "cost_usd": 0.1,
                "model_usage": {
                    "claude-opus-4-8": {
                        "input_tokens": True,
                        "output_tokens": 1,
                    }
                },
            },
        )
        spec_path, receipts_path = self._write(tmp_path, spec, receipts)
        out = tmp_path / "report.json"

        assert (
            main(
                [
                    "--spec",
                    str(spec_path),
                    "--receipts",
                    str(receipts_path),
                    "--output",
                    str(out),
                ]
            )
            == 2
        )
        assert not out.exists()

    def test_malformed_model_name_is_rejected_without_reflection(
        self, tmp_path, capsys
    ):
        spec = make_spec()
        receipts = full_receipts(spec)
        target = receipts[0]
        secret = "Bearer SECRET-SENTINEL"
        receipts[0] = make_receipt(
            spec,
            target.trial.task_id,
            target.trial.arm,
            target.trial.repetition,
            usage={
                "source": "sdk_model_usage",
                "cost_usd": 0.1,
                "model_usage": {
                    secret: {
                        "input_tokens": 1,
                        "output_tokens": 1,
                    }
                },
            },
        )
        spec_path, receipts_path = self._write(tmp_path, spec, receipts)
        out = tmp_path / "report.json"

        assert (
            main(
                [
                    "--spec",
                    str(spec_path),
                    "--receipts",
                    str(receipts_path),
                    "--output",
                    str(out),
                ]
            )
            == 2
        )
        assert not out.exists()
        assert "SECRET-SENTINEL" not in capsys.readouterr().err

    def test_huge_token_count_fails_before_writing_output(self, tmp_path):
        spec = make_spec()
        receipts = full_receipts(spec)
        target = receipts[0]
        receipts[0] = make_receipt(
            spec,
            target.trial.task_id,
            target.trial.arm,
            target.trial.repetition,
            usage={
                "source": "sdk_model_usage",
                "cost_usd": 0.1,
                "model_usage": {
                    "claude-opus-4-8": {
                        "input_tokens": 10**4000,
                        "output_tokens": 1,
                    }
                },
            },
        )
        spec_path, receipts_path = self._write(tmp_path, spec, receipts)
        out = tmp_path / "report.json"

        assert (
            main(
                [
                    "--spec",
                    str(spec_path),
                    "--receipts",
                    str(receipts_path),
                    "--output",
                    str(out),
                ]
            )
            == 2
        )
        assert not out.exists()

    def test_nonfinite_report_number_fails_strict_json_serialization(
        self, tmp_path, monkeypatch
    ):
        spec = make_spec()
        spec_path, receipts_path = self._write(tmp_path, spec, full_receipts(spec))
        out = tmp_path / "report.json"
        monkeypatch.setattr(
            study_report_module,
            "build_report",
            lambda _capsule, **_kwargs: {"not_json": float("nan")},
        )

        assert (
            main(
                [
                    "--spec",
                    str(spec_path),
                    "--receipts",
                    str(receipts_path),
                    "--output",
                    str(out),
                ]
            )
            == 2
        )
        assert not out.exists()
