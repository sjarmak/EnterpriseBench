"""Locked statistical-analysis contract for capsule study reports."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from analysis.study_inference import (  # noqa: E402
    AnalysisContract,
    bootstrap_mean_difference,
    build_inference,
    holm_adjust,
    load_analysis_contract,
)
from eb_study import CapsuleError, StudySpec, file_hash  # noqa: E402
from tests.test_study_capsule import make_spec  # noqa: E402


def _contract() -> AnalysisContract:
    return AnalysisContract(
        plan_hash="sha256:plan",
        manifest_hash="sha256:manifest",
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
        task_types={
            "dep-1": "dependency_graph",
            "dep-2": "dependency_graph",
            "err-1": "error_provenance",
            "inc-1": "incident_investigation",
        },
    )


def _scores() -> dict[str, dict[str, float]]:
    return {
        "dep-1": {"baseline": 0.50, "mcp_only": 0.60, "cli": 0.54},
        "dep-2": {"baseline": 0.70, "mcp_only": 0.65, "cli": 0.72},
        "err-1": {"baseline": 0.40, "mcp_only": 0.55, "cli": 0.42},
        "inc-1": {"baseline": 0.80, "mcp_only": 0.75, "cli": 0.79},
    }


class TestPairedBootstrap:
    def test_constant_paired_difference_has_a_point_interval(self):
        result = bootstrap_mean_difference(
            [0.5, 0.5, 0.5],
            [0.6, 0.6, 0.6],
            repetitions=10_000,
            seed=20_260_728,
            confidence_levels=(0.95, 0.90),
        )

        assert result["mean_delta"] == pytest.approx(0.1)
        assert result["confidence_intervals"]["0.95"] == {
            "low": pytest.approx(0.1),
            "high": pytest.approx(0.1),
        }
        assert result["confidence_intervals"]["0.9"] == {
            "low": pytest.approx(0.1),
            "high": pytest.approx(0.1),
        }
        assert result["p_value_two_sided_centered_bootstrap"] == pytest.approx(
            1 / 10_001
        )

    def test_seeded_result_is_reproducible(self):
        kwargs = {
            "repetitions": 10_000,
            "seed": 20_260_728,
            "confidence_levels": (0.95, 0.90),
        }

        first = bootstrap_mean_difference(
            [0.1, 0.4, 0.8, 0.2],
            [0.5, 0.3, 0.9, 0.4],
            **kwargs,
        )
        second = bootstrap_mean_difference(
            [0.1, 0.4, 0.8, 0.2],
            [0.5, 0.3, 0.9, 0.4],
            **kwargs,
        )

        assert first == second

    @pytest.mark.parametrize(
        ("baseline", "candidate"),
        (
            ([], []),
            ([0.1], [0.1, 0.2]),
            ([0.1, float("nan")], [0.1, 0.2]),
        ),
    )
    def test_invalid_samples_fail_closed(self, baseline, candidate):
        with pytest.raises(CapsuleError):
            bootstrap_mean_difference(
                baseline,
                candidate,
                repetitions=10_000,
                seed=20_260_728,
                confidence_levels=(0.95,),
            )


def test_holm_adjustment_is_monotone_in_rank_order():
    adjusted = holm_adjust(
        {
            "mcp_only_vs_baseline": 0.01,
            "cli_vs_baseline": 0.04,
        }
    )

    assert adjusted == {
        "mcp_only_vs_baseline": pytest.approx(0.02),
        "cli_vs_baseline": pytest.approx(0.04),
    }


class TestInferenceReport:
    def test_complete_study_emits_locked_primary_and_type_stratified_analysis(self):
        inference = build_inference(
            per_task_scores=_scores(),
            contract=_contract(),
            complete=True,
        )

        assert inference["status"] == "complete"
        assert inference["method"] == {
            "bootstrap_repetitions": 10_000,
            "bootstrap_seed": 20_260_728,
            "bootstrap_unit": "paired_task",
            "bootstrap_sampling": "within_task_type_fixed_stratum_sizes",
            "prng": "sha256_counter_rejection_v1",
            "quantile_method": "linear_type_7",
            "interval": "percentile",
            "primary_confidence_level": 0.95,
            "parity_confidence_level": 0.90,
            "multiplicity": "holm",
            "familywise_alpha": 0.05,
            "significance_testing": ("withheld_raw_p_value_estimator_not_frozen"),
        }
        assert set(inference["primary"]) == {
            "mcp_only_vs_baseline",
            "cli_vs_baseline",
        }
        assert inference["primary"]["mcp_only_vs_baseline"]["n_paired"] == 4
        assert (
            "holm_adjusted_p_value"
            not in (inference["primary"]["mcp_only_vs_baseline"])
        )
        assert (
            "reject_null_fwer_0_05"
            not in (inference["primary"]["mcp_only_vs_baseline"])
        )
        assert (
            "p_value_two_sided_centered_bootstrap"
            not in (inference["primary"]["mcp_only_vs_baseline"])
        )
        assert inference["primary"]["cli_vs_baseline"]["parity"][
            "absolute_task_score_margin"
        ] == pytest.approx(0.05)
        assert inference["descriptive_only"]["contrast"] == "cli_vs_mcp_only"
        assert inference["descriptive_only"]["confirmatory_claim_eligible"] is False
        assert inference["by_task_type"]["dependency_graph"]["n_tasks"] == 2
        assert inference["by_task_type"]["error_provenance"]["n_tasks"] == 1
        assert inference["by_task_type"]["incident_investigation"]["n_tasks"] == 1
        assert set(inference["by_task_type"]["dependency_graph"]["contrasts"]) == {
            "mcp_only_vs_baseline",
            "cli_vs_baseline",
        }
        assert all(
            "p_value_two_sided_centered_bootstrap" not in result
            for stratum in inference["by_task_type"].values()
            for result in stratum["contrasts"].values()
        )

    def test_primary_bootstrap_preserves_every_locked_stratum_size(self):
        scores = {
            "dep-1": {"baseline": 0.5, "mcp_only": 0.7, "cli": 0.5},
            "dep-2": {"baseline": 0.5, "mcp_only": 0.7, "cli": 0.5},
            "err-1": {"baseline": 0.5, "mcp_only": 0.3, "cli": 0.5},
            "inc-1": {"baseline": 0.5, "mcp_only": 0.3, "cli": 0.5},
        }

        inference = build_inference(
            per_task_scores=scores,
            contract=_contract(),
            complete=True,
        )

        primary = inference["primary"]["mcp_only_vs_baseline"]
        assert primary["mean_delta"] == pytest.approx(0.0)
        assert primary["confidence_interval_95"] == {
            "low": pytest.approx(0.0),
            "high": pytest.approx(0.0),
        }

    def test_incomplete_study_withholds_all_confirmatory_inference(self):
        scores = _scores()
        scores.pop("inc-1")

        inference = build_inference(
            per_task_scores=scores,
            contract=_contract(),
            complete=False,
        )

        assert inference == {
            "status": "withheld_incomplete",
            "analysis_plan_hash": "sha256:plan",
            "task_manifest_hash": "sha256:manifest",
            "declared_tasks": 4,
            "paired_tasks": 3,
            "missing_task_ids": ["inc-1"],
            "reason": (
                "confirmatory inference requires every declared task to be "
                "paired and valid"
            ),
        }


def _write_contract_files(
    tmp_path: Path,
    spec: StudySpec,
) -> tuple[Path, Path]:
    plan_path = tmp_path / "analysis_plan.json"
    plan = {
        "schema_version": 1,
        "status": "LOCKED-BEFORE-HEADLINE-INFERENCE",
        "study_id": spec.study_id,
        "score": {
            "field": "task_score",
            "contract": spec.score_contract,
            "range": [0.0, 1.0],
            "unit": "task",
        },
        "primary_estimands": [
            {
                "name": "mcp_only_minus_baseline",
                "contrast": ["mcp_only", "baseline"],
                "aggregation": "unweighted mean",
            },
            {
                "name": "cli_minus_baseline",
                "contrast": ["cli", "baseline"],
                "aggregation": "unweighted mean",
            },
        ],
        "descriptive_only": {
            "contrast": "cli_minus_mcp_only",
            "reason": "interface and source availability both change",
        },
        "inference": {
            "confidence_level": 0.95,
            "bootstrap_repetitions": 10_000,
            "bootstrap_seed": 20_260_728,
            "bootstrap_unit": "paired task",
            "stratification": "task_type with locked observed stratum sizes",
            "interval": "percentile paired bootstrap",
            "multiplicity": (
                "Holm correction at familywise alpha 0.05 for the two primary contrasts"
            ),
        },
        "reward_parity_gate_for_efficiency_claims": {
            "method": ("two one-sided tests using a 90% paired-bootstrap interval"),
            "absolute_task_score_margin": 0.05,
            "claim_rule": "interval within margin",
        },
        "missing_invalid_handling": {
            "max_attempts_per_slot": spec.max_attempts,
            "retry_after_observing_output_or_score": False,
            f"headline_requires_all_{len(spec.slots())}_slots_valid": True,
            "incomplete_pair": "no headline promotion or confirmatory inference",
            "all_attempts": "retain status, tokens, elapsed time, and cost",
        },
        "reporting": {
            "type_counts_and_per_type_results_required": True,
            "absolute_arm_means_required": True,
            "paired_differences_and_intervals_required": True,
            "all_attempt_spend_required": True,
            "account_order_and_revision_provenance_required": True,
            "no_generalization_to_structured_deliverables": True,
        },
    }
    plan_path.write_text(json.dumps(plan, indent=2) + "\n")
    manifest_path = tmp_path / "final_manifest.json"
    manifest = {
        "schema_version": 1,
        "status": "FINAL-NO-SPEND",
        "study_id": spec.study_id,
        "analysis_plan_hash": file_hash(plan_path),
        "tasks": [
            {
                "task_id": task_id,
                "task_type": ("dependency_graph" if index == 0 else "error_provenance"),
            }
            for index, task_id in enumerate(spec.task_ids)
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return plan_path, manifest_path


class TestAnalysisContract:
    def test_repository_v6_contract_exposes_readable_frozen_provenance(self):
        study_dir = PROJECT_ROOT / "configs" / "studies" / "rryas-headline-v6"
        spec = StudySpec.load(study_dir / "study_spec.json")

        contract = load_analysis_contract(
            spec,
            study_dir / "analysis_plan.json",
            study_dir / "final_manifest.json",
        )

        assert contract.candidate_manifest_hash == (
            "sha256:007d332e94d729208cf4a0d3307bc800d12b57c1c09da5703f644812d0d9450d"
        )
        assert contract.candidate_lock_revision == (
            "bb60d7e11cbdc77ae94e54dfcaceb7d975ed3e6e"
        )
        assert contract.execution_order_hash.startswith("sha256:")
        assert contract.execution_order_count == 90
        assert contract.agent_account == 3
        assert contract.judge_account == 1
        assert contract.stratum_counts == {
            "dependency_graph": 13,
            "error_provenance": 3,
            "incident_investigation": 14,
        }
        assert contract.task_hashes["dep-traversal-001"].startswith("sha256:")
        assert contract.verifier_hashes["dep-traversal-001"].startswith("sha256:")

    def test_loads_plan_only_when_manifest_and_spec_bind_its_exact_bytes(
        self, tmp_path
    ):
        provisional = make_spec()
        plan_path, manifest_path = _write_contract_files(tmp_path, provisional)
        spec_payload = provisional.to_json()
        spec_payload["task_manifest_hash"] = file_hash(manifest_path)
        spec = StudySpec.from_json(spec_payload)

        contract = load_analysis_contract(spec, plan_path, manifest_path)

        assert contract.plan_hash == file_hash(plan_path)
        assert contract.manifest_hash == file_hash(manifest_path)
        assert contract.task_types == {
            "dep-traversal-001": "dependency_graph",
            "dep-traversal-002": "error_provenance",
        }

    @pytest.mark.parametrize(
        ("document", "block"),
        (
            ("manifest", "arms"),
            ("manifest", "cache_isolation"),
            ("manifest", "evidence_policy"),
            ("manifest", "spend_guard"),
            ("manifest", "verifier_hashes"),
            ("plan", "protocol_amendment"),
        ),
    )
    def test_repository_contract_rejects_unknown_nested_fields(
        self, tmp_path, document, block
    ):
        study_dir = PROJECT_ROOT / "configs" / "studies" / "rryas-headline-v6"
        plan = json.loads((study_dir / "analysis_plan.json").read_text())
        manifest = json.loads((study_dir / "final_manifest.json").read_text())
        target = manifest if document == "manifest" else plan
        target[block]["post_hoc_override"] = True

        plan_path = tmp_path / "analysis_plan.json"
        plan_path.write_text(json.dumps(plan, indent=2) + "\n")
        manifest["analysis_plan_hash"] = file_hash(plan_path)
        manifest_path = tmp_path / "final_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        spec_payload = StudySpec.load(study_dir / "study_spec.json").to_json()
        spec_payload["task_manifest_hash"] = file_hash(manifest_path)
        spec = StudySpec.from_json(spec_payload)

        with pytest.raises(CapsuleError, match="unknown|does not match"):
            load_analysis_contract(spec, plan_path, manifest_path)

    @pytest.mark.parametrize(
        "mutation",
        (
            "manifest_bytes",
            "analysis_plan_bytes",
            "task_type_missing",
            "study_id",
            "bootstrap_repetitions",
            "duplicate_plan_key",
            "unknown_plan_key",
            "unknown_manifest_selection_key",
        ),
    )
    def test_contract_tampering_fails_closed(self, tmp_path, mutation):
        provisional = make_spec()
        plan_path, manifest_path = _write_contract_files(tmp_path, provisional)
        spec_payload = provisional.to_json()
        spec_payload["task_manifest_hash"] = file_hash(manifest_path)
        spec = StudySpec.from_json(spec_payload)

        if mutation == "manifest_bytes":
            manifest = json.loads(manifest_path.read_text())
            manifest["tasks"][0]["task_type"] = "incident_investigation"
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        elif mutation == "analysis_plan_bytes":
            plan = json.loads(plan_path.read_text())
            plan["inference"]["bootstrap_seed"] += 1
            plan_path.write_text(json.dumps(plan, indent=2) + "\n")
        elif mutation == "task_type_missing":
            manifest = json.loads(manifest_path.read_text())
            manifest["tasks"][0].pop("task_type")
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
            spec_payload["task_manifest_hash"] = file_hash(manifest_path)
            spec = StudySpec.from_json(spec_payload)
        elif mutation == "study_id":
            plan = json.loads(plan_path.read_text())
            plan["study_id"] = "other-study"
            plan_path.write_text(json.dumps(plan, indent=2) + "\n")
            manifest = json.loads(manifest_path.read_text())
            manifest["analysis_plan_hash"] = file_hash(plan_path)
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
            spec_payload["task_manifest_hash"] = file_hash(manifest_path)
            spec = StudySpec.from_json(spec_payload)
        elif mutation == "bootstrap_repetitions":
            plan = json.loads(plan_path.read_text())
            plan["inference"]["bootstrap_repetitions"] = 100
            plan_path.write_text(json.dumps(plan, indent=2) + "\n")
            manifest = json.loads(manifest_path.read_text())
            manifest["analysis_plan_hash"] = file_hash(plan_path)
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
            spec_payload["task_manifest_hash"] = file_hash(manifest_path)
            spec = StudySpec.from_json(spec_payload)
        elif mutation == "duplicate_plan_key":
            source = plan_path.read_text()
            plan_path.write_text(
                source.replace(
                    '"bootstrap_seed": 20260728,',
                    ('"bootstrap_seed": 20260728,\n    "bootstrap_seed": 20260728,'),
                )
            )
            manifest = json.loads(manifest_path.read_text())
            manifest["analysis_plan_hash"] = file_hash(plan_path)
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
            spec_payload["task_manifest_hash"] = file_hash(manifest_path)
            spec = StudySpec.from_json(spec_payload)
        elif mutation == "unknown_plan_key":
            plan = json.loads(plan_path.read_text())
            plan["inference"]["post_hoc_override"] = True
            plan_path.write_text(json.dumps(plan, indent=2) + "\n")
            manifest = json.loads(manifest_path.read_text())
            manifest["analysis_plan_hash"] = file_hash(plan_path)
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
            spec_payload["task_manifest_hash"] = file_hash(manifest_path)
            spec = StudySpec.from_json(spec_payload)
        elif mutation == "unknown_manifest_selection_key":
            manifest = json.loads(manifest_path.read_text())
            manifest["selection"] = {
                "rule": "locked without inspecting outcomes",
                "candidate_outcomes_inspected": False,
                "candidate_count": len(spec.task_ids),
                "selected_count": len(spec.task_ids),
                "post_lock_exposures": [],
                "post_hoc_override": True,
            }
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
            spec_payload["task_manifest_hash"] = file_hash(manifest_path)
            spec = StudySpec.from_json(spec_payload)

        with pytest.raises(CapsuleError):
            load_analysis_contract(spec, plan_path, manifest_path)

    def test_oversized_parity_margin_is_a_domain_error(self, tmp_path):
        provisional = make_spec()
        plan_path, manifest_path = _write_contract_files(tmp_path, provisional)
        plan = json.loads(plan_path.read_text())
        plan["reward_parity_gate_for_efficiency_claims"][
            "absolute_task_score_margin"
        ] = 10**4000
        plan_path.write_text(json.dumps(plan, indent=2) + "\n")
        manifest = json.loads(manifest_path.read_text())
        manifest["analysis_plan_hash"] = file_hash(plan_path)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        spec_payload = provisional.to_json()
        spec_payload["task_manifest_hash"] = file_hash(manifest_path)
        spec = StudySpec.from_json(spec_payload)

        with pytest.raises(CapsuleError, match="finite"):
            load_analysis_contract(spec, plan_path, manifest_path)
