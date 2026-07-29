"""Tests for the RunPromotionOrchestrator.

The tests stub the read-only validators and the score/chart/report
generators so the orchestrator can be exercised without real benchmark
data. The orchestrator under test is a sequencer with rollback hooks —
the unit tests cover the contract (atomicity, resume, validate-only,
forensics) rather than the upstream tools' behaviour.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "orchestration"))

import run_promotion_orchestrator as rpo  # noqa: E402
import promotion_capsule  # noqa: E402
from eb_study import StudySpec, file_hash  # noqa: E402
from tests.test_study_capsule import make_receipt, make_spec  # noqa: E402
from tests.test_study_inference import _write_contract_files  # noqa: E402


@pytest.fixture
def workdir(tmp_path: Path) -> Path:
    """Create a fake repo layout inside a temporary directory."""
    raw_runs = tmp_path / "results" / "runs"
    raw_runs.mkdir(parents=True)
    official_runs = tmp_path / "results" / "official_runs"
    official_runs.mkdir(parents=True)
    return tmp_path


def _make_run(workdir: Path, run_id: str) -> Path:
    raw_run_dir = workdir / "results" / "runs" / run_id
    raw_run_dir.mkdir(parents=True)
    provisional = make_spec(
        study_id=run_id,
        task_ids=["t1"],
        repetitions=1,
        max_attempts=1,
    )
    study_config = workdir / "configs" / "studies" / run_id
    study_config.mkdir(parents=True)
    _plan_path, manifest_path = _write_contract_files(
        study_config,
        provisional,
    )
    spec_payload = provisional.to_json()
    spec_payload["task_manifest_hash"] = file_hash(manifest_path)
    spec = StudySpec.from_json(spec_payload)
    (raw_run_dir / "study_spec.json").write_text(json.dumps(spec.to_json()))
    receipts = [make_receipt(spec, "t1", arm, 1) for arm in spec.arm_names]
    (raw_run_dir / "receipts.jsonl").write_text(
        "".join(json.dumps(receipt.to_json()) + "\n" for receipt in receipts)
    )
    return raw_run_dir


def _make_ctx(workdir: Path, run_id: str, **overrides: Any) -> rpo.PromotionContext:
    base = rpo.build_context(
        run_id=run_id,
        target_state="official",
        repo_root=workdir,
        raw_runs_root=workdir / "results" / "runs",
        official_runs_root=workdir / "results" / "official_runs",
        study_report_path=REPO_ROOT / "scripts" / "analysis" / "study_report.py",
    )
    if overrides:
        base = replace(base, **overrides)
    return base


def _step(name: str, fail: bool = False) -> rpo.Step:
    """Build a synthetic step that creates a marker file or raises."""
    marker_state: dict[str, Path] = {}

    def execute(ctx: rpo.PromotionContext) -> rpo.StepOutcome:
        if fail:
            raise RuntimeError(f"step {name} failed by design")
        ctx.staging_dir.mkdir(parents=True, exist_ok=True)
        marker = ctx.staging_dir / f"{name}.marker"
        marker.write_text(name)
        marker_state[name] = marker
        return rpo.StepOutcome(
            step_name=name, status="reversible", details=f"created {marker.name}"
        )

    def rollback(_ctx: rpo.PromotionContext) -> None:
        marker = marker_state.get(name)
        if marker and marker.is_file():
            marker.unlink()

    return rpo.Step(name=name, execute=execute, rollback=rollback)


class TestContext:
    def test_orchestrator_supports_package_style_import(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import scripts.orchestration.run_promotion_orchestrator",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, result.stderr

    def test_step_name_alone_does_not_trigger_capsule_io(self, workdir: Path) -> None:
        ctx = _make_ctx(workdir, "missing")
        pipeline = [
            rpo.Step(
                "validate_inputs",
                lambda _ctx: rpo.StepOutcome("validate_inputs", "reversible"),
            )
        ]

        report = rpo.RunPromotionOrchestrator(ctx, pipeline).run()

        assert report.succeeded

    def test_invalid_target_state_raises(self, workdir: Path) -> None:
        ctx = _make_ctx(workdir, "r1", target_state="bogus")
        with pytest.raises(ValueError, match="Invalid target_state"):
            rpo.RunPromotionOrchestrator(ctx)

    def test_negative_resume_from_raises(self, workdir: Path) -> None:
        ctx = _make_ctx(workdir, "r1", resume_from=-1)
        with pytest.raises(ValueError, match="resume_from must be >= 0"):
            rpo.RunPromotionOrchestrator(ctx)

    @pytest.mark.parametrize("run_id", ["..", "sub/..", "a/b", "/tmp/escape"])
    def test_run_id_cannot_escape_promotion_roots(
        self, workdir: Path, run_id: str
    ) -> None:
        with pytest.raises(ValueError, match="run_id"):
            rpo.build_context(
                run_id=run_id,
                target_state="official",
                repo_root=workdir,
            )

    def test_resume_cannot_skip_capsule_revalidation(self, workdir: Path) -> None:
        ctx = _make_ctx(workdir, "r1", resume_from=6)
        with pytest.raises(ValueError, match="resume_from"):
            rpo.RunPromotionOrchestrator(ctx)

    def test_default_pipeline_has_nine_steps(self) -> None:
        pipeline = rpo.build_default_pipeline()
        names = [s.name for s in pipeline]
        assert names == [
            "validate_inputs",
            "validate_tasks_preflight",
            "validate_crnt",
            "validate_expected_solutions",
            "stage_metrics",
            "stage_charts",
            "stage_report",
            "atomic_publish",
            "update_registry",
        ]


class TestValidateOnly:
    def test_validate_only_runs_only_validators(self, workdir: Path) -> None:
        _make_run(workdir, "r1")
        ctx = _make_ctx(workdir, "r1")
        validators = [
            rpo.Step(
                "validate_a", lambda c: rpo.StepOutcome("validate_a", "reversible")
            ),
            rpo.Step(
                "validate_b", lambda c: rpo.StepOutcome("validate_b", "reversible")
            ),
            _step("stage_x", fail=False),
        ]
        report = rpo.RunPromotionOrchestrator(ctx, validators).run(validate_only=True)
        assert report.succeeded
        assert [s.step_name for s in report.steps] == ["validate_a", "validate_b"]
        assert not ctx.staging_dir.exists()

    def test_validation_failure_writes_no_forensics(self, workdir: Path) -> None:
        ctx = _make_ctx(workdir, "r1")
        report = rpo.RunPromotionOrchestrator(
            ctx,
            [_step("validate_crash", fail=True)],
        ).run(validate_only=True)

        assert not report.succeeded
        assert report.forensics_path is None
        assert not ctx.forensics_dir.exists()


class TestAtomicPublish:
    def test_publish_renames_staging_to_final(self, workdir: Path) -> None:
        _make_run(workdir, "r1")
        ctx = _make_ctx(workdir, "r1")
        rpo._step_stage_metrics(ctx)
        rpo._step_stage_report(ctx)

        outcome = rpo._step_atomic_publish(ctx)
        assert outcome.status == "reversible"
        assert ctx.final_dir.is_dir()
        assert (ctx.final_dir / "score_analysis.json").is_file()
        assert (ctx.final_dir / "promotion_seal.json").is_file()
        assert not ctx.staging_dir.exists()
        assert ctx.final_dir.stat().st_mode & 0o777 == 0o555
        assert all(
            path.stat().st_mode & 0o777 == 0o444 for path in ctx.final_dir.iterdir()
        )

    def test_publish_refuses_existing_final(self, workdir: Path) -> None:
        _make_run(workdir, "r1")
        ctx = _make_ctx(workdir, "r1")
        ctx.staging_dir.mkdir(parents=True)
        ctx.final_dir.mkdir(parents=True)

        with pytest.raises(RuntimeError, match="final dir already exists"):
            rpo._step_atomic_publish(ctx)

    def test_publish_dry_run_does_not_move(self, workdir: Path) -> None:
        _make_run(workdir, "r1")
        ctx = _make_ctx(workdir, "r1", dry_run=True)
        ctx.staging_dir.mkdir(parents=True)

        outcome = rpo._step_atomic_publish(ctx)
        assert outcome.status == "dry_run"
        assert ctx.staging_dir.exists()
        assert not ctx.final_dir.exists()


class TestRollback:
    def test_failure_rolls_back_completed_steps_lifo(self, workdir: Path) -> None:
        rollback_order: list[str] = []

        def make_step(name: str, fail: bool = False) -> rpo.Step:
            def execute(ctx: rpo.PromotionContext) -> rpo.StepOutcome:
                if fail:
                    raise RuntimeError(f"{name} failed")
                ctx.staging_dir.mkdir(parents=True, exist_ok=True)
                (ctx.staging_dir / f"{name}.marker").write_text(name)
                return rpo.StepOutcome(name, "reversible")

            def rollback(_ctx: rpo.PromotionContext) -> None:
                rollback_order.append(name)

            return rpo.Step(name=name, execute=execute, rollback=rollback)

        ctx = _make_ctx(workdir, "r1")
        pipeline = [
            make_step("a"),
            make_step("b"),
            make_step("c", fail=True),
        ]
        report = rpo.RunPromotionOrchestrator(ctx, pipeline).run()
        assert not report.succeeded
        # Failed step (c) never produced a reversible outcome — only a/b roll back.
        assert rollback_order == ["b", "a"]

    def test_staging_rollback_removes_directory(self, workdir: Path) -> None:
        ctx = _make_ctx(workdir, "r1")
        ctx.staging_dir.mkdir(parents=True)
        (ctx.staging_dir / "x").write_text("x")
        rpo._rollback_staging(ctx)
        assert not ctx.staging_dir.exists()

    def test_publish_rollback_returns_dir_to_staging(self, workdir: Path) -> None:
        ctx = _make_ctx(workdir, "r1")
        ctx.final_dir.mkdir(parents=True)
        (ctx.final_dir / "x").write_text("x")
        rpo._rollback_atomic_publish(ctx)
        assert ctx.staging_dir.is_dir()
        assert (ctx.staging_dir / "x").read_text() == "x"
        assert not ctx.final_dir.exists()


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------


class TestResume:
    def test_resume_never_skips_validation_steps(self, workdir: Path) -> None:
        _make_run(workdir, "r1")
        executed: list[str] = []

        def step(name: str) -> rpo.Step:
            def execute(_ctx: rpo.PromotionContext) -> rpo.StepOutcome:
                executed.append(name)
                return rpo.StepOutcome(name, "reversible")

            return rpo.Step(name=name, execute=execute)

        ctx = _make_ctx(workdir, "r1", resume_from=5)
        pipeline = [
            step("validate_inputs"),
            step("validate_tasks"),
            step("validate_crnt"),
            step("validate_expected_solutions"),
            step("stage_metrics"),
        ]

        report = rpo.RunPromotionOrchestrator(ctx, pipeline).run()

        assert report.succeeded
        assert executed == [
            "validate_inputs",
            "validate_tasks",
            "validate_crnt",
            "validate_expected_solutions",
            "stage_metrics",
        ]

    def test_resume_from_step_skips_earlier_steps(self, workdir: Path) -> None:
        executed: list[str] = []

        def step(name: str) -> rpo.Step:
            def execute(_ctx: rpo.PromotionContext) -> rpo.StepOutcome:
                executed.append(name)
                return rpo.StepOutcome(name, "reversible")

            return rpo.Step(name=name, execute=execute)

        ctx = _make_ctx(workdir, "r1", resume_from=3)
        pipeline = [step("a"), step("b"), step("c"), step("d")]
        report = rpo.RunPromotionOrchestrator(ctx, pipeline).run()
        assert report.succeeded
        # Only steps 3 and 4 actually executed.
        assert executed == ["c", "d"]
        # Skipped steps appear in the report with status "skipped".
        statuses = {s.step_name: s.status for s in report.steps}
        assert statuses["a"] == "skipped"
        assert statuses["b"] == "skipped"
        assert statuses["c"] == "reversible"
        assert statuses["d"] == "reversible"


# ---------------------------------------------------------------------------
# Validate inputs
# ---------------------------------------------------------------------------


class TestValidateInputs:
    def test_missing_run_dir_raises(self, workdir: Path) -> None:
        ctx = _make_ctx(workdir, "missing")
        with pytest.raises(FileNotFoundError):
            rpo._step_validate_inputs(ctx)

    def test_empty_run_dir_raises(self, workdir: Path) -> None:
        ctx = _make_ctx(workdir, "empty")
        ctx.raw_run_dir.mkdir(parents=True)
        with pytest.raises(ValueError, match="empty"):
            rpo._step_validate_inputs(ctx)

    def test_populated_run_dir_passes(self, workdir: Path) -> None:
        _make_run(workdir, "good")
        ctx = _make_ctx(workdir, "good")
        outcome = rpo._step_validate_inputs(ctx)
        assert outcome.status == "reversible"

    def test_study_id_must_match_the_promoted_run(self, workdir: Path) -> None:
        run_dir = _make_run(workdir, "good")
        spec = json.loads((run_dir / "study_spec.json").read_text())
        spec["study_id"] = "different-study"
        (run_dir / "study_spec.json").write_text(json.dumps(spec))

        with pytest.raises(ValueError, match="study_id"):
            rpo._step_validate_inputs(_make_ctx(workdir, "good"))

    def test_duplicate_spec_key_fails_closed(self, workdir: Path) -> None:
        run_dir = _make_run(workdir, "good")
        spec_path = run_dir / "study_spec.json"
        source = spec_path.read_text().replace(
            '"study_id": "good"',
            '"study_id": "shadow", "study_id": "good"',
            1,
        )
        spec_path.write_text(source)

        with pytest.raises(ValueError, match="duplicate JSON object key"):
            rpo._step_validate_inputs(_make_ctx(workdir, "good"))

    def test_missing_declared_arm_fails_closed(self, workdir: Path) -> None:
        run_dir = _make_run(workdir, "good")
        receipts_path = run_dir / "receipts.jsonl"
        receipts = receipts_path.read_text().splitlines()
        receipts_path.write_text("\n".join(receipts[:-1]) + "\n")

        with pytest.raises(ValueError, match="incomplete"):
            rpo._step_validate_inputs(_make_ctx(workdir, "good"))


class TestReadOnlyValidators:
    def test_declared_task_ids_resolve_to_exact_task_files(self, workdir: Path) -> None:
        _make_run(workdir, "r1")
        task_dir = workdir / "benchmarks" / "suite" / "t1"
        task_dir.mkdir(parents=True)
        task_toml = task_dir / "task.toml"
        task_toml.write_text('[task]\nid = "t1"\n')

        assert rpo._declared_task_tomls(_make_ctx(workdir, "r1")) == (task_toml,)

    def test_duplicate_declared_task_ids_fail_closed(self, workdir: Path) -> None:
        _make_run(workdir, "r1")
        for suite in ("a", "b"):
            task_dir = workdir / "benchmarks" / suite / "t1"
            task_dir.mkdir(parents=True)
            (task_dir / "task.toml").write_text('[task]\nid = "t1"\n')

        with pytest.raises(RuntimeError, match="2 matches"):
            rpo._declared_task_tomls(_make_ctx(workdir, "r1"))

    def test_malformed_task_candidate_fails_closed(self, workdir: Path) -> None:
        _make_run(workdir, "r1")
        task_dir = workdir / "benchmarks" / "suite" / "broken"
        task_dir.mkdir(parents=True)
        (task_dir / "task.toml").write_text("[task\n")

        with pytest.raises(RuntimeError, match="cannot read"):
            rpo._declared_task_tomls(_make_ctx(workdir, "r1"))

    @pytest.mark.parametrize(
        ("step", "script_name"),
        [
            (rpo._step_validate_tasks_preflight, "validate_tasks_preflight.py"),
            (rpo._step_validate_crnt, "crnt_validator.py"),
            (
                rpo._step_validate_expected_solutions,
                "validate_expected_solutions.py",
            ),
        ],
    )
    def test_success_is_recorded(
        self,
        workdir: Path,
        monkeypatch: pytest.MonkeyPatch,
        step,
        script_name: str,
    ) -> None:
        calls: list[list[str]] = []

        def succeed(cmd: list[str], _cwd: Path) -> tuple[int, str, str]:
            calls.append(cmd)
            return 0, "", ""

        monkeypatch.setattr(rpo, "_run_subprocess", succeed)
        if step is rpo._step_validate_crnt:
            monkeypatch.setattr(
                rpo,
                "_declared_task_tomls",
                lambda _ctx: (workdir / "benchmarks" / "task.toml",),
            )

        outcome = step(_make_ctx(workdir, "r1"))

        assert outcome.status == "reversible"
        assert script_name in " ".join(calls[0])
        if step is rpo._step_validate_crnt:
            assert "--all" not in calls[0]

    @pytest.mark.parametrize(
        "step",
        [
            rpo._step_validate_tasks_preflight,
            rpo._step_validate_crnt,
            rpo._step_validate_expected_solutions,
        ],
    )
    def test_failure_aborts_with_stderr(
        self,
        workdir: Path,
        monkeypatch: pytest.MonkeyPatch,
        step,
    ) -> None:
        monkeypatch.setattr(
            rpo,
            "_run_subprocess",
            lambda _cmd, _cwd: (2, "", "validator exploded"),
        )
        if step is rpo._step_validate_crnt:
            monkeypatch.setattr(
                rpo,
                "_declared_task_tomls",
                lambda _ctx: (workdir / "benchmarks" / "task.toml",),
            )

        with pytest.raises(RuntimeError, match="validator exploded"):
            step(_make_ctx(workdir, "r1"))


# ---------------------------------------------------------------------------
# Stage metrics
# ---------------------------------------------------------------------------


def _fake_analyzer(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[list[str]],
    total_results: int = 3,
    payload: str | None = None,
) -> None:
    """Stub the in-process report builder while preserving its real default."""

    real_builder = promotion_capsule.build_report

    def fake(capsule: Any, **kwargs: Any) -> Any:
        calls.append([capsule.spec.study_id, *capsule.spec.task_ids])
        if payload is not None:
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                return payload
        report = real_builder(capsule, **kwargs)
        report["completeness"]["paired_tasks"] = total_results
        report["completeness"]["declared_tasks"] = total_results
        return report

    monkeypatch.setattr(promotion_capsule, "build_report", fake)


class TestStageMetrics:
    def test_source_capsule_replacement_after_validation_fails_closed(
        self, workdir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        run_dir = _make_run(workdir, "r1")
        ctx = _make_ctx(workdir, "r1")
        _fake_analyzer(monkeypatch, [])

        def replace_capsule(_ctx: rpo.PromotionContext) -> rpo.StepOutcome:
            replacement = make_spec(
                study_id="r1",
                task_ids=["t2"],
                repetitions=1,
                max_attempts=1,
            )
            (run_dir / "study_spec.json").write_text(json.dumps(replacement.to_json()))
            receipts = [
                make_receipt(replacement, "t2", arm, 1) for arm in replacement.arm_names
            ]
            (run_dir / "receipts.jsonl").write_text(
                "".join(json.dumps(receipt.to_json()) + "\n" for receipt in receipts)
            )
            return rpo.StepOutcome("replace_capsule", "reversible")

        def wrapped_validate(ctx: rpo.PromotionContext) -> rpo.StepOutcome:
            return rpo._step_validate_inputs(ctx)

        report = rpo.RunPromotionOrchestrator(
            ctx,
            [
                rpo.Step("validate_inputs", wrapped_validate, bind_capsule=True),
                rpo.Step("replace_capsule", replace_capsule),
                rpo.Step("stage_metrics", rpo._step_stage_metrics),
            ],
        ).run()

        assert not report.succeeded
        assert "changed after validation" in report.error
        assert not (ctx.staging_dir / "score_analysis.json").exists()

    def test_real_report_ignores_higher_scoring_unrelated_capsule(
        self, workdir: Path
    ) -> None:
        _make_run(workdir, "r1")
        unrelated = _make_run(workdir, "quarantined")
        unrelated_receipts = unrelated / "receipts.jsonl"
        payloads = [
            json.loads(line) for line in unrelated_receipts.read_text().splitlines()
        ]
        for payload in payloads:
            payload["score"] = 1.0
        unrelated_receipts.write_text(
            "".join(json.dumps(payload) + "\n" for payload in payloads)
        )
        ctx = replace(
            _make_ctx(workdir, "r1"),
            study_report_path=REPO_ROOT / "scripts" / "analysis" / "study_report.py",
        )

        outcome = rpo._step_stage_metrics(ctx)

        report = json.loads((ctx.staging_dir / "score_analysis.json").read_text())
        assert outcome.status == "reversible"
        assert report["provenance"]["study_id"] == "r1"
        assert report["completeness"]["paired_tasks"] == 1
        assert report["reward"]["by_arm"]["baseline"]["mean"] == pytest.approx(0.5)

    def test_analyzer_receives_only_the_named_capsule(
        self, workdir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _make_run(workdir, "r1")
        # A second, unrelated run must not be visible to the analyzer.
        _make_run(workdir, "quarantined")
        ctx = _make_ctx(workdir, "r1")
        calls: list[list[str]] = []
        _fake_analyzer(monkeypatch, calls)

        outcome = rpo._step_stage_metrics(ctx)

        assert outcome.status == "reversible"
        assert calls == [["r1", "t1"]]
        assert (ctx.staging_dir / "study_spec.json").read_bytes() == (
            ctx.spec_path.read_bytes()
        )
        assert (ctx.staging_dir / "receipts.jsonl").read_bytes() == (
            ctx.receipts_path.read_bytes()
        )
        assert (
            "quarantined" not in (ctx.staging_dir / "score_analysis.json").read_text()
        )

    def test_analysis_plan_replacement_after_validation_fails_closed(
        self,
        workdir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _make_run(workdir, "r1")
        ctx = _make_ctx(workdir, "r1")
        _fake_analyzer(monkeypatch, [])

        def replace_plan(_ctx: rpo.PromotionContext) -> rpo.StepOutcome:
            _ctx.analysis_plan_path.write_text("{}")
            return rpo.StepOutcome("replace_plan", "reversible")

        report = rpo.RunPromotionOrchestrator(
            ctx,
            [
                rpo.Step(
                    "validate_inputs", rpo._step_validate_inputs, bind_capsule=True
                ),
                rpo.Step("replace_plan", replace_plan),
                rpo.Step("stage_metrics", rpo._step_stage_metrics),
            ],
        ).run()

        assert not report.succeeded
        assert "changed after validation" in report.error
        assert not (ctx.staging_dir / "score_analysis.json").exists()

    def test_incomplete_analysis_is_rejected(
        self, workdir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _make_run(workdir, "r1")
        ctx = _make_ctx(workdir, "r1")
        _fake_analyzer(monkeypatch, [], total_results=0)

        with pytest.raises(RuntimeError, match="no paired tasks"):
            rpo._step_stage_metrics(ctx)

    def test_unreadable_analysis_is_rejected(
        self, workdir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _make_run(workdir, "r1")
        ctx = _make_ctx(workdir, "r1")
        _fake_analyzer(monkeypatch, [], payload="not json")

        with pytest.raises(RuntimeError, match="unreadable"):
            rpo._step_stage_metrics(ctx)

    def test_report_for_a_different_study_is_rejected(
        self, workdir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _make_run(workdir, "r1")
        ctx = _make_ctx(workdir, "r1")
        payload = json.dumps(
            {
                "schema_version": 3,
                "analysis": {"status": "complete"},
                "provenance": {"study_id": "other", "spec_hash": "sha256:other"},
                "completeness": {
                    "paired_tasks": 1,
                    "declared_tasks": 1,
                    "excluded_tasks": {},
                },
            }
        )
        _fake_analyzer(monkeypatch, [], payload=payload)

        with pytest.raises(RuntimeError, match="study_id"):
            rpo._step_stage_metrics(ctx)

    def test_report_for_a_different_analysis_plan_is_rejected(
        self,
        workdir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _make_run(workdir, "r1")
        ctx = _make_ctx(workdir, "r1")
        spec = StudySpec.load(ctx.spec_path)
        payload = json.dumps(
            {
                "schema_version": 3,
                "analysis": {"status": "complete"},
                "provenance": {
                    "study_id": spec.study_id,
                    "spec_hash": spec.spec_hash,
                    "analysis_plan_hash": "sha256:wrong",
                    "task_manifest_hash": file_hash(ctx.task_manifest_path),
                    "study_spec_file_hash": file_hash(ctx.spec_path),
                    "receipts_file_hash": file_hash(ctx.receipts_path),
                },
                "completeness": {
                    "paired_tasks": 1,
                    "declared_tasks": 1,
                    "excluded_tasks": {},
                },
            }
        )
        _fake_analyzer(monkeypatch, [], payload=payload)

        with pytest.raises(RuntimeError, match="analysis plan"):
            rpo._step_stage_metrics(ctx)

    def test_report_without_exact_source_hashes_is_rejected(
        self,
        workdir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _make_run(workdir, "r1")
        ctx = _make_ctx(workdir, "r1")
        spec = StudySpec.load(ctx.spec_path)
        payload = json.dumps(
            {
                "schema_version": 3,
                "analysis": {"status": "complete"},
                "provenance": {
                    "study_id": spec.study_id,
                    "spec_hash": spec.spec_hash,
                    "analysis_plan_hash": file_hash(ctx.analysis_plan_path),
                    "task_manifest_hash": file_hash(ctx.task_manifest_path),
                },
                "completeness": {
                    "paired_tasks": 1,
                    "declared_tasks": 1,
                    "excluded_tasks": {},
                },
            }
        )
        _fake_analyzer(monkeypatch, [], payload=payload)

        with pytest.raises(RuntimeError, match="source hashes"):
            rpo._step_stage_metrics(ctx)


class TestNamedStudyPromotionE2E:
    def test_capsule_is_validated_reported_and_published_atomically(
        self, workdir: Path
    ) -> None:
        _make_run(workdir, "r1")
        ctx = replace(
            _make_ctx(workdir, "r1"),
            study_report_path=REPO_ROOT / "scripts" / "analysis" / "study_report.py",
        )
        pipeline = [
            rpo.Step("validate_inputs", rpo._step_validate_inputs),
            rpo.Step(
                "stage_metrics",
                rpo._step_stage_metrics,
                rollback=rpo._rollback_staging,
            ),
            rpo.Step("stage_charts", rpo._step_stage_charts),
            rpo.Step("stage_report", rpo._step_stage_report),
            rpo.Step(
                "atomic_publish",
                rpo._step_atomic_publish,
                rollback=rpo._rollback_atomic_publish,
            ),
            rpo.Step(
                "update_registry",
                rpo._step_update_registry,
                rollback=rpo._rollback_noop,
            ),
        ]

        report = rpo.RunPromotionOrchestrator(ctx, pipeline).run()

        assert report.succeeded
        assert ctx.final_dir.is_dir()
        promoted = json.loads((ctx.final_dir / "score_analysis.json").read_text())
        assert promoted["provenance"]["study_id"] == "r1"
        assert (ctx.final_dir / "study_spec.json").is_file()
        assert (ctx.final_dir / "receipts.jsonl").is_file()
        assert not ctx.staging_dir.exists()

    def test_staged_contract_mutation_before_atomic_publish_fails_closed(
        self,
        workdir: Path,
    ) -> None:
        _make_run(workdir, "r1")
        ctx = replace(
            _make_ctx(workdir, "r1"),
            study_report_path=REPO_ROOT / "scripts" / "analysis" / "study_report.py",
        )

        def mutate_staged_plan(_ctx: rpo.PromotionContext) -> rpo.StepOutcome:
            (_ctx.staging_dir / "analysis_plan.json").write_text("{}")
            return rpo.StepOutcome("mutate_staged_plan", "reversible")

        report = rpo.RunPromotionOrchestrator(
            ctx,
            [
                rpo.Step("validate_inputs", rpo._step_validate_inputs),
                rpo.Step("stage_metrics", rpo._step_stage_metrics),
                rpo.Step("mutate_staged_plan", mutate_staged_plan),
                rpo.Step("atomic_publish", rpo._step_atomic_publish),
            ],
        ).run()

        assert not report.succeeded
        assert "staged capsule seal" in report.error
        assert not ctx.final_dir.exists()

    def test_staged_report_mutation_before_atomic_publish_fails_closed(
        self,
        workdir: Path,
    ) -> None:
        _make_run(workdir, "r1")
        ctx = replace(
            _make_ctx(workdir, "r1"),
            study_report_path=REPO_ROOT / "scripts" / "analysis" / "study_report.py",
        )

        def mutate_report(_ctx: rpo.PromotionContext) -> rpo.StepOutcome:
            path = _ctx.staging_dir / "score_analysis.json"
            payload = json.loads(path.read_text())
            payload["reward"]["by_arm"]["baseline"]["mean"] = 0.999
            path.write_text(json.dumps(payload))
            return rpo.StepOutcome("mutate_report", "reversible")

        report = rpo.RunPromotionOrchestrator(
            ctx,
            [
                rpo.Step("validate_inputs", rpo._step_validate_inputs),
                rpo.Step("stage_metrics", rpo._step_stage_metrics),
                rpo.Step("stage_report", rpo._step_stage_report),
                rpo.Step("mutate_report", mutate_report),
                rpo.Step("atomic_publish", rpo._step_atomic_publish),
            ],
        ).run()

        assert not report.succeeded
        assert "promotion seal" in report.error
        assert not ctx.final_dir.exists()


# ---------------------------------------------------------------------------
# Registry update
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_first_promotion_creates_registry(self, workdir: Path) -> None:
        ctx = _make_ctx(workdir, "r1")
        ctx.final_dir.mkdir(parents=True)

        outcome = rpo._step_update_registry(ctx)
        assert outcome.status == "forward_only"
        registry = json.loads(ctx.registry_path.read_text())
        assert len(registry["entries"]) == 1
        assert registry["entries"][0]["run_id"] == "r1"

    def test_reentry_replaces_existing(self, workdir: Path) -> None:
        ctx = _make_ctx(workdir, "r1")
        ctx.final_dir.mkdir(parents=True)
        ctx.registry_path.parent.mkdir(parents=True, exist_ok=True)
        ctx.registry_path.write_text(
            json.dumps(
                {
                    "entries": [
                        {"run_id": "r1", "target_state": "candidate"},
                        {"run_id": "r2", "target_state": "official"},
                    ]
                }
            )
        )

        rpo._step_update_registry(ctx)
        registry = json.loads(ctx.registry_path.read_text())
        run_ids = [e["run_id"] for e in registry["entries"]]
        # r2 preserved, r1 replaced (single entry per run_id).
        assert run_ids == ["r2", "r1"]
        assert registry["entries"][1]["target_state"] == "official"

    def test_dry_run_does_not_write(self, workdir: Path) -> None:
        ctx = _make_ctx(workdir, "r1", dry_run=True)
        outcome = rpo._step_update_registry(ctx)
        assert outcome.status == "dry_run"
        assert not ctx.registry_path.exists()

    def test_preexisting_registry_temp_symlink_cannot_overwrite_victim(
        self,
        workdir: Path,
    ) -> None:
        ctx = _make_ctx(workdir, "r1")
        ctx.final_dir.mkdir(parents=True)
        victim = workdir / "registry-victim.json"
        victim.write_text("must survive\n")
        fixed_temp = ctx.registry_path.with_suffix(ctx.registry_path.suffix + ".tmp")
        fixed_temp.symlink_to(victim)

        rpo._step_update_registry(ctx)

        assert victim.read_text() == "must survive\n"
        assert ctx.registry_path.is_file()
        assert not ctx.registry_path.is_symlink()

    def test_registry_target_symlink_is_rejected_without_touching_victim(
        self,
        workdir: Path,
    ) -> None:
        ctx = _make_ctx(workdir, "r1")
        ctx.final_dir.mkdir(parents=True)
        victim = workdir / "registry-target-victim.json"
        victim.write_text('{"entries": []}\n')
        ctx.registry_path.symlink_to(victim)

        with pytest.raises(RuntimeError, match="regular artifact"):
            rpo._step_update_registry(ctx)

        assert victim.read_text() == '{"entries": []}\n'


# ---------------------------------------------------------------------------
# Forensics
# ---------------------------------------------------------------------------


class TestForensics:
    def test_failure_writes_forensic_snapshot(self, workdir: Path) -> None:
        ctx = _make_ctx(workdir, "r1")
        pipeline = [
            _step("a"),
            _step("crash", fail=True),
        ]
        report = rpo.RunPromotionOrchestrator(ctx, pipeline).run()
        assert not report.succeeded
        assert report.forensics_path is not None
        forensics = Path(report.forensics_path)
        assert forensics.is_dir()
        assert (forensics / "context.json").is_file()
        assert (forensics / "error.json").is_file()
        assert (forensics / "completed_steps.json").is_file()

        err = json.loads((forensics / "error.json").read_text())
        assert err["type"] == "RuntimeError"
        assert "crash failed" in err["message"]

    def test_forensics_uses_exclusive_files_and_redacts_failure_secrets(
        self,
        workdir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ctx = _make_ctx(workdir, "r1")
        fixed = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)

        class FixedDateTime:
            @staticmethod
            def now(_tz: timezone) -> datetime:
                return fixed

        monkeypatch.setattr(rpo, "datetime", FixedDateTime)
        predictable = ctx.forensics_dir / "r1_20260729T120000Z"
        predictable.mkdir(parents=True)
        victim = workdir / "forensics-victim.json"
        victim.write_text("must survive\n")
        (predictable / "error.json").symlink_to(victim)

        def fail(_ctx: rpo.PromotionContext) -> rpo.StepOutcome:
            raise RuntimeError("Bearer SECRET-SENTINEL-SECOND")

        report = rpo.RunPromotionOrchestrator(
            ctx,
            [rpo.Step("fail", fail)],
        ).run()

        assert not report.succeeded
        assert victim.read_text() == "must survive\n"
        assert report.forensics_path is not None
        forensic_dir = Path(report.forensics_path)
        assert forensic_dir != predictable
        error = (forensic_dir / "error.json").read_text()
        assert "SECRET-SENTINEL" not in error
        assert "[REDACTED]" in error


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------


class TestCli:
    def test_cli_reports_failure_on_missing_run(
        self, workdir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Force the orchestrator to use the workdir-rooted layout.
        original_repo_root = rpo.REPO_ROOT
        rpo.REPO_ROOT = workdir
        try:
            rc = rpo.main(
                [
                    "--run-id",
                    "does-not-exist",
                    "--validate-only",
                    "--json",
                ]
            )
        finally:
            rpo.REPO_ROOT = original_repo_root

        assert rc == 1
        captured = capsys.readouterr().out
        report = json.loads(captured)
        assert report["succeeded"] is False
        assert report["run_id"] == "does-not-exist"
