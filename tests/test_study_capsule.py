"""Contract tests for the promotion-grade study capsule.

The properties under test are the ones a paid headline run depends on: a
receipt cannot join a study it was not part of, an unmeasured trial cannot
carry a number, an arm cannot disappear from a comparison, and no admission
rule anywhere reads the score.
"""

from __future__ import annotations

import json

import pytest

from eb_study import (
    CapsuleIntegrityError,
    CompletenessError,
    ReceiptError,
    SpecError,
    StudyCapsule,
    StudySpec,
    TrialReceipt,
    append_receipt,
    read_receipts,
)

ARMS = ("baseline", "mcp_only", "cli")


def spec_payload(**overrides):
    payload = {
        "study_id": "rryas-headline-2026-07",
        "schema_version": 1,
        "task_manifest_hash": "sha256:manifest",
        "task_ids": ["dep-traversal-001", "dep-traversal-002"],
        "arms": [
            {"name": "baseline", "capability_fingerprint": "no-tools"},
            {"name": "mcp_only", "capability_fingerprint": "sourcegraph-mcp@v1"},
            {"name": "cli", "capability_fingerprint": "sgx@v2"},
        ],
        "baseline_arm": "baseline",
        "repetitions": 2,
        "attempt_policy": "all_valid_repetitions",
        "max_attempts": 3,
        "model": "claude-opus-4-8",
        "harness": "run_task.py@sha256:harness",
        "revision": "e439534",
        "token_source": "sdk_model_usage",
        "score_contract": "weighted-checkpoints-v1",
        "promotion_policy": "paired-valid-complete-arms",
    }
    payload.update(overrides)
    return payload


def make_spec(**overrides) -> StudySpec:
    return StudySpec.from_json(spec_payload(**overrides))


def receipt_payload(spec: StudySpec, task_id: str, arm: str, rep: int, **overrides):
    payload = {
        "schema_version": 1,
        "trial": {
            "study_id": spec.study_id,
            "task_id": task_id,
            "arm": arm,
            "repetition": rep,
            "attempt": 1,
        },
        "spec_hash": spec.spec_hash,
        "task_manifest_hash": spec.task_manifest_hash,
        "status": "valid",
        "failure_class": None,
        "image_digest": "sha256:image",
        "arm_gate_proof": "mode_gate:agent-denied,scorer-allowed",
        "task_hash": "sha256:task",
        "harness_hash": "sha256:harness",
        "verifier_hash": "sha256:verifier",
        "score": 0.5,
        "score_contract": spec.score_contract,
        "usage": {
            "source": "sdk_model_usage",
            "cost_usd": 1.25,
            "model_usage": {"claude-opus-4-8": {"inputTokens": 10, "outputTokens": 20}},
        },
        "tool_use": {"sgx_tool_calls": 4},
        "artifacts": {"agent_trace.jsonl": "sha256:trace"},
        "started_at": "2026-07-20T00:00:00Z",
        "ended_at": "2026-07-20T00:10:00Z",
    }
    trial_overrides = overrides.pop("trial", None)
    if trial_overrides:
        payload["trial"].update(trial_overrides)
    payload.update(overrides)
    return payload


def make_receipt(spec: StudySpec, task_id: str, arm: str, rep: int, **overrides):
    return TrialReceipt.from_json(receipt_payload(spec, task_id, arm, rep, **overrides))


def full_receipts(spec: StudySpec) -> list[TrialReceipt]:
    return [
        make_receipt(spec, task_id, arm, rep)
        for task_id in spec.task_ids
        for arm in spec.arm_names
        for rep in range(1, spec.repetitions + 1)
    ]


# ---------------------------------------------------------------------------
# StudySpec
# ---------------------------------------------------------------------------


class TestStudySpec:
    @pytest.mark.parametrize("field", sorted(spec_payload().keys()))
    def test_every_frozen_field_is_required(self, field):
        payload = spec_payload()
        del payload[field]
        with pytest.raises(SpecError):
            StudySpec.from_json(payload)

    def test_unsupported_schema_version_is_refused(self):
        with pytest.raises(SpecError, match="schema_version"):
            StudySpec.from_json(spec_payload(schema_version=99))

    def test_attempt_policy_must_be_declared(self):
        with pytest.raises(SpecError, match="attempt_policy"):
            StudySpec.from_json(spec_payload(attempt_policy="highest_score"))

    def test_token_source_must_be_authoritative(self):
        with pytest.raises(SpecError, match="token_source"):
            StudySpec.from_json(spec_payload(token_source="trace"))

    def test_baseline_must_be_a_declared_arm(self):
        with pytest.raises(SpecError, match="baseline_arm"):
            StudySpec.from_json(spec_payload(baseline_arm="hybrid"))

    def test_duplicate_arms_are_refused(self):
        arms = spec_payload()["arms"]
        with pytest.raises(SpecError, match="duplicate arm"):
            StudySpec.from_json(spec_payload(arms=arms + [arms[0]]))

    def test_contrasts_include_every_non_baseline_arm(self):
        assert make_spec().contrast_arms == ("mcp_only", "cli")

    def test_slots_cover_task_by_arm_by_repetition(self):
        spec = make_spec()
        assert len(spec.slots()) == 2 * 3 * 2
        assert ("dep-traversal-001", "cli", 2) in spec.slots()

    def test_hash_changes_when_any_frozen_field_changes(self):
        assert make_spec().spec_hash != make_spec(model="claude-sonnet-5").spec_hash

    def test_trial_id_refuses_undeclared_coordinates(self):
        spec = make_spec()
        with pytest.raises(SpecError, match="not declared"):
            spec.trial_id("dep-traversal-001", "hybrid", 1, 1)
        with pytest.raises(SpecError, match="repetition"):
            spec.trial_id("dep-traversal-001", "cli", 9, 1)


# ---------------------------------------------------------------------------
# TrialReceipt
# ---------------------------------------------------------------------------


class TestTrialReceipt:
    @pytest.mark.parametrize(
        "field",
        [
            "image_digest",
            "arm_gate_proof",
            "task_hash",
            "harness_hash",
            "verifier_hash",
            "score_contract",
        ],
    )
    def test_valid_trial_must_carry_every_provenance_field(self, field):
        spec = make_spec()
        with pytest.raises(ReceiptError, match="missing required provenance"):
            make_receipt(spec, "dep-traversal-001", "cli", 1, **{field: None})

    def test_valid_trial_must_carry_a_score(self):
        spec = make_spec()
        with pytest.raises(ReceiptError, match="carries no score"):
            make_receipt(spec, "dep-traversal-001", "cli", 1, score=None)

    def test_valid_trial_must_carry_authoritative_usage(self):
        spec = make_spec()
        with pytest.raises(ReceiptError, match="no authoritative usage"):
            make_receipt(spec, "dep-traversal-001", "cli", 1, usage=None)

    def test_infra_invalid_trial_must_name_a_failure_class(self):
        spec = make_spec()
        with pytest.raises(ReceiptError, match="names no failure_class"):
            make_receipt(
                spec, "dep-traversal-001", "cli", 1, status="infra_invalid", score=None
            )

    def test_infra_invalid_trial_may_not_carry_a_score(self):
        spec = make_spec()
        with pytest.raises(ReceiptError, match="has no score to report"):
            make_receipt(
                spec,
                "dep-traversal-001",
                "cli",
                1,
                status="infra_invalid",
                failure_class="repo_clone_failed",
                score=0.0,
            )

    def test_infra_invalid_trial_still_records_its_spend(self):
        """The run cost money even though it measured nothing."""

        spec = make_spec()
        receipt = make_receipt(
            spec,
            "dep-traversal-001",
            "cli",
            1,
            status="infra_invalid",
            failure_class="judge_unavailable",
            score=None,
        )
        assert receipt.usage is not None
        assert receipt.usage.cost_usd == 1.25

    def test_score_outside_the_unit_interval_is_refused(self):
        """A weighted score re-divided by checkpoint count lands here."""

        spec = make_spec()
        with pytest.raises(ReceiptError, match="outside 0..1"):
            make_receipt(spec, "dep-traversal-001", "cli", 1, score=2.5)

    def test_artifacts_must_be_content_addressed(self):
        spec = make_spec()
        with pytest.raises(ReceiptError, match="sha256"):
            make_receipt(
                spec, "dep-traversal-001", "cli", 1, artifacts={"trace": "/tmp/trace"}
            )


class TestAppendOnlyLog:
    def test_roundtrip(self, tmp_path):
        spec = make_spec()
        path = tmp_path / "receipts.jsonl"
        for receipt in full_receipts(spec):
            append_receipt(path, receipt)
        assert len(read_receipts(path)) == len(spec.slots())

    def test_a_trial_cannot_be_rewritten(self, tmp_path):
        spec = make_spec()
        path = tmp_path / "receipts.jsonl"
        receipt = make_receipt(spec, "dep-traversal-001", "cli", 1)
        append_receipt(path, receipt)
        with pytest.raises(ReceiptError, match="append-only"):
            append_receipt(path, make_receipt(spec, "dep-traversal-001", "cli", 1, score=0.9))

    def test_a_malformed_line_fails_the_whole_log(self, tmp_path):
        path = tmp_path / "receipts.jsonl"
        path.write_text("{not json}\n")
        with pytest.raises(ReceiptError, match="not valid JSON"):
            read_receipts(path)

    def test_line_number_is_reported(self, tmp_path):
        spec = make_spec()
        path = tmp_path / "receipts.jsonl"
        append_receipt(path, make_receipt(spec, "dep-traversal-001", "cli", 1))
        with path.open("a") as handle:
            handle.write(json.dumps({"schema_version": 1}) + "\n")
        with pytest.raises(ReceiptError, match=":2:"):
            read_receipts(path)


# ---------------------------------------------------------------------------
# Capsule integrity
# ---------------------------------------------------------------------------


class TestCapsuleIntegrity:
    def test_receipt_from_another_study_is_refused(self):
        spec = make_spec()
        other = make_spec(study_id="smoke-run")
        with pytest.raises(CapsuleIntegrityError, match="belongs to study"):
            StudyCapsule.build(spec, [make_receipt(other, "dep-traversal-001", "cli", 1)])

    def test_receipt_from_an_edited_spec_is_refused(self):
        spec = make_spec()
        stale = make_receipt(spec, "dep-traversal-001", "cli", 1, spec_hash="sha256:stale")
        with pytest.raises(CapsuleIntegrityError, match="spec hash"):
            StudyCapsule.build(spec, [stale])

    def test_receipt_naming_another_task_manifest_is_refused(self):
        spec = make_spec()
        drifted = make_receipt(
            spec, "dep-traversal-001", "cli", 1, task_manifest_hash="sha256:other"
        )
        with pytest.raises(CapsuleIntegrityError, match="task manifest"):
            StudyCapsule.build(spec, [drifted])

    def test_receipt_for_an_undeclared_task_is_refused(self):
        spec = make_spec()
        payload = receipt_payload(spec, "dep-traversal-001", "cli", 1)
        payload["trial"]["task_id"] = "quarantined-task-999"
        with pytest.raises(CapsuleIntegrityError, match="not in study"):
            StudyCapsule.build(spec, [TrialReceipt.from_json(payload)])

    def test_receipt_scored_under_another_contract_is_refused(self):
        spec = make_spec()
        legacy = make_receipt(
            spec, "dep-traversal-001", "cli", 1, score_contract="renormalized-v0"
        )
        with pytest.raises(CapsuleIntegrityError, match="score contract|contract"):
            StudyCapsule.build(spec, [legacy])

    def test_receipt_billed_from_the_trace_is_refused(self):
        spec = make_spec()
        payload = receipt_payload(spec, "dep-traversal-001", "cli", 1)
        payload["usage"]["source"] = "trace"
        with pytest.raises(CapsuleIntegrityError, match="bills usage"):
            StudyCapsule.build(spec, [TrialReceipt.from_json(payload)])

    def test_duplicate_trial_is_refused(self):
        spec = make_spec()
        receipt = make_receipt(spec, "dep-traversal-001", "cli", 1)
        with pytest.raises(CapsuleIntegrityError, match="duplicate receipt"):
            StudyCapsule.build(spec, [receipt, receipt])

    def test_empty_capsule_is_refused(self):
        with pytest.raises(CapsuleIntegrityError, match="no receipts"):
            StudyCapsule.build(make_spec(), [])

    def test_load_from_disk(self, tmp_path):
        spec = make_spec()
        spec_path = tmp_path / "study.json"
        spec_path.write_text(json.dumps(spec.to_json()))
        receipts_path = tmp_path / "receipts.jsonl"
        for receipt in full_receipts(spec):
            append_receipt(receipts_path, receipt)

        capsule = StudyCapsule.load(spec_path, receipts_path)
        assert capsule.paired_valid().task_ids == spec.task_ids


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


class TestPairedValid:
    def test_complete_study_pairs_every_task_in_every_arm(self):
        spec = make_spec()
        paired = StudyCapsule.build(spec, full_receipts(spec)).paired_valid()
        assert paired.task_ids == spec.task_ids
        assert paired.arms == ARMS
        assert len(paired.trials) == len(spec.slots())
        assert paired.excluded == {}

    def test_a_missing_arm_fails_the_comparison(self):
        """The CLI arm must not quietly become a two-arm result."""

        spec = make_spec()
        receipts = [r for r in full_receipts(spec) if r.trial.arm != "cli"]
        with pytest.raises(CompletenessError, match=r"\['cli'\]"):
            StudyCapsule.build(spec, receipts).paired_valid()

    def test_an_invalid_receipt_does_not_fill_its_slot(self):
        spec = make_spec()
        receipts = [r for r in full_receipts(spec) if r.trial.arm != "cli"]
        receipts += [
            make_receipt(
                spec,
                task_id,
                "cli",
                rep,
                status="infra_invalid",
                failure_class="repo_clone_failed",
                score=None,
            )
            for task_id in spec.task_ids
            for rep in (1, 2)
        ]
        with pytest.raises(CompletenessError, match=r"\['cli'\]"):
            StudyCapsule.build(spec, receipts).paired_valid()

    def test_a_task_missing_one_repetition_is_excluded_and_named(self):
        spec = make_spec()
        receipts = [
            r
            for r in full_receipts(spec)
            if not (r.trial.task_id == "dep-traversal-002" and r.trial.arm == "cli" and r.trial.repetition == 2)
        ]
        paired = StudyCapsule.build(spec, receipts).paired_valid()
        assert paired.task_ids == ("dep-traversal-001",)
        assert paired.excluded == {"dep-traversal-002": ("cli/rep2",)}

    def test_no_complete_task_fails_rather_than_reporting_nothing(self):
        spec = make_spec()
        receipts = [r for r in full_receipts(spec) if r.trial.repetition == 1]
        with pytest.raises(CompletenessError, match="no task complete"):
            StudyCapsule.build(spec, receipts).paired_valid()

    def test_mean_score_averages_repetitions_rather_than_taking_the_best(self):
        spec = make_spec()
        receipts = [
            r
            for r in full_receipts(spec)
            if not (r.trial.task_id == "dep-traversal-001" and r.trial.arm == "cli")
        ]
        receipts.append(make_receipt(spec, "dep-traversal-001", "cli", 1, score=0.2))
        receipts.append(make_receipt(spec, "dep-traversal-001", "cli", 2, score=1.0))

        paired = StudyCapsule.build(spec, receipts).paired_valid()
        assert paired.mean_score("dep-traversal-001", "cli") == pytest.approx(0.6)

    def test_paired_cost_excludes_invalid_spend(self):
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
        capsule = StudyCapsule.build(spec, receipts)
        assert capsule.paired_valid().cost_usd == pytest.approx(12 * 1.25)
        assert capsule.all_attempts().cost_usd == pytest.approx(13 * 1.25)


class TestAttemptPolicy:
    def test_all_valid_repetitions_refuses_two_valid_attempts_in_one_slot(self):
        spec = make_spec()
        receipts = full_receipts(spec)
        receipts.append(
            make_receipt(spec, "dep-traversal-001", "cli", 1, score=0.99, trial={"attempt": 2})
        )
        with pytest.raises(CapsuleIntegrityError, match="valid attempts"):
            StudyCapsule.build(spec, receipts).paired_valid()

    def test_first_valid_attempt_ignores_the_better_rerun(self):
        spec = make_spec(attempt_policy="first_valid_attempt")
        receipts = full_receipts(spec)
        receipts.append(
            make_receipt(spec, "dep-traversal-001", "cli", 1, score=0.99, trial={"attempt": 2})
        )
        paired = StudyCapsule.build(spec, receipts).paired_valid()
        admitted = [
            t
            for t in paired.trials
            if t.trial.task_id == "dep-traversal-001"
            and t.trial.arm == "cli"
            and t.trial.repetition == 1
        ]
        assert [t.trial.attempt for t in admitted] == [1]
        assert admitted[0].score == 0.5

    def test_a_failed_first_attempt_lets_the_retry_stand(self):
        spec = make_spec(attempt_policy="first_valid_attempt")
        receipts = [
            r
            for r in full_receipts(spec)
            if not (r.trial.task_id == "dep-traversal-001" and r.trial.arm == "cli" and r.trial.repetition == 1)
        ]
        receipts.append(
            make_receipt(
                spec,
                "dep-traversal-001",
                "cli",
                1,
                status="infra_invalid",
                failure_class="repo_clone_failed",
                score=None,
            )
        )
        receipts.append(
            make_receipt(spec, "dep-traversal-001", "cli", 1, score=0.4, trial={"attempt": 2})
        )
        paired = StudyCapsule.build(spec, receipts).paired_valid()
        assert paired.task_ids == spec.task_ids
        assert paired.mean_score("dep-traversal-001", "cli") == pytest.approx(0.45)


class TestAllAttempts:
    def test_every_receipt_is_counted_by_status(self):
        spec = make_spec()
        receipts = full_receipts(spec)
        receipts.append(
            make_receipt(
                spec,
                "dep-traversal-002",
                "mcp_only",
                1,
                status="ineligible",
                failure_class="code_patch_task_under_gated_arm",
                score=None,
                trial={"attempt": 2},
            )
        )
        counts = StudyCapsule.build(spec, receipts).all_attempts().count_by_status
        assert counts == {"ineligible": 1, "valid": 12}
