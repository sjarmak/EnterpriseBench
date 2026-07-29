"""End-to-end publication artifact and sealing tests."""

import json
import os
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from eb_study import CapsuleError, StudyCapsule, TrialReceipt, file_hash
from tests.test_run_promotion_orchestrator import (
    _fake_analyzer,
    _make_ctx,
    _make_run,
    rpo as unit_rpo,
)

from scripts.orchestration import run_promotion_orchestrator as rpo
from scripts.orchestration import promotion_capsule, publication_fs


def _fake_analysis_tools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    tools_dir = tmp_path / "analysis-tools"
    tools_dir.mkdir()
    analyzer = tools_dir / "study_report.py"
    renderer = tools_dir / "study_markdown_report.py"
    analyzer.write_text("# frozen analyzer v1\n")
    renderer.write_text("# frozen renderer v1\n")

    calls: list[list[str]] = []
    _fake_analyzer(monkeypatch, calls)
    analyze = unit_rpo._run_subprocess

    def dispatch(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
        if "--spec" in cmd:
            return analyze(cmd, cwd)
        output = Path(cmd[cmd.index("--output") + 1])
        output.write_text("# Publication report\n")
        return 0, "", ""

    monkeypatch.setattr(rpo, "_run_subprocess", dispatch)
    return analyzer


def _bind_task_contract(
    ctx: rpo.PromotionContext,
    task_path: Path,
    declared_path: str,
) -> rpo.CapsuleSnapshot:
    snapshot = rpo._capsule_snapshot(ctx)
    expected_hash = file_hash(task_path)
    receipts = tuple(
        replace(receipt, task_hash=expected_hash)
        for receipt in snapshot.capsule.receipts
    )
    return replace(
        snapshot,
        capsule=StudyCapsule.build(snapshot.spec, receipts),
        analysis_contract=replace(
            snapshot.analysis_contract,
            task_hashes={"t1": expected_hash},
            task_paths={"t1": declared_path},
        ),
    )


def test_capsule_stage_report_writes_markdown_and_refreshes_seal(
    tmp_path: Path,
) -> None:
    workdir = tmp_path
    (workdir / "results" / "runs").mkdir(parents=True)
    (workdir / "results" / "official_runs").mkdir(parents=True)
    _make_run(workdir, "r1")
    ctx = _make_ctx(workdir, "r1")

    rpo._step_stage_metrics(ctx)
    outcome = rpo._step_stage_report(ctx)

    report_path = ctx.staging_dir / "report.md"
    assert outcome.status == "reversible"
    assert report_path.is_file()
    assert "## Primary paired results" in report_path.read_text()
    seal = (ctx.staging_dir / "promotion_seal.json").read_text()
    assert '"report.md"' in seal
    assert '"report_renderer_hash"' in seal


def test_atomic_publish_refuses_missing_publication_markdown(tmp_path: Path) -> None:
    workdir = tmp_path
    (workdir / "results" / "runs").mkdir(parents=True)
    (workdir / "results" / "official_runs").mkdir(parents=True)
    _make_run(workdir, "r1")
    ctx = _make_ctx(workdir, "r1")
    rpo._step_stage_metrics(ctx)

    with pytest.raises(RuntimeError, match="report.md"):
        rpo._step_atomic_publish(ctx)


def test_atomic_publish_refuses_markdown_mutated_after_sealing(tmp_path: Path) -> None:
    workdir = tmp_path
    (workdir / "results" / "runs").mkdir(parents=True)
    (workdir / "results" / "official_runs").mkdir(parents=True)
    _make_run(workdir, "r1")
    ctx = _make_ctx(workdir, "r1")
    rpo._step_stage_metrics(ctx)
    rpo._step_stage_report(ctx)
    (ctx.staging_dir / "report.md").write_text("tampered\n")

    with pytest.raises(RuntimeError, match="promotion seal"):
        rpo._step_atomic_publish(ctx)


def test_stage_report_rejects_unknown_analysis_fields(tmp_path: Path) -> None:
    (tmp_path / "results" / "runs").mkdir(parents=True)
    (tmp_path / "results" / "official_runs").mkdir(parents=True)
    _make_run(tmp_path, "r1")
    ctx = _make_ctx(tmp_path, "r1")
    rpo._step_stage_metrics(ctx)
    analysis_path = ctx.staging_dir / "score_analysis.json"
    analysis = json.loads(analysis_path.read_text())
    analysis["post_hoc_override"] = True
    analysis_path.write_text(json.dumps(analysis))

    with pytest.raises(RuntimeError, match="unknown"):
        rpo._step_stage_report(ctx)


def test_staging_symlink_is_rejected_before_any_artifact_write(
    tmp_path: Path,
) -> None:
    workdir = tmp_path / "repo"
    (workdir / "results" / "runs").mkdir(parents=True)
    (workdir / "results" / "official_runs").mkdir(parents=True)
    _make_run(workdir, "r1")
    ctx = _make_ctx(workdir, "r1")
    attacker_dir = tmp_path / "attacker"
    attacker_dir.mkdir()
    ctx.staging_dir.parent.mkdir(parents=True, exist_ok=True)
    ctx.staging_dir.symlink_to(attacker_dir, target_is_directory=True)

    with pytest.raises(RuntimeError, match="staging.*symlink"):
        rpo._step_stage_metrics(ctx)

    assert list(attacker_dir.iterdir()) == []


def test_staging_ancestor_symlink_is_rejected_before_any_artifact_write(
    tmp_path: Path,
) -> None:
    workdir = tmp_path / "repo"
    workdir.mkdir()
    attacker_results = tmp_path / "attacker-results"
    (attacker_results / "runs").mkdir(parents=True)
    (attacker_results / "official_runs").mkdir()
    (workdir / "results").symlink_to(attacker_results, target_is_directory=True)
    _make_run(workdir, "r1")
    ctx = _make_ctx(workdir, "r1")

    with pytest.raises(RuntimeError, match="symlink|trusted repository"):
        rpo._step_stage_metrics(ctx)

    assert not ctx.staging_dir.exists()


def test_stage_metrics_refuses_preexisting_artifact_symlink(
    tmp_path: Path,
) -> None:
    (tmp_path / "results" / "runs").mkdir(parents=True)
    (tmp_path / "results" / "official_runs").mkdir(parents=True)
    _make_run(tmp_path, "r1")
    ctx = _make_ctx(tmp_path, "r1")
    ctx.staging_dir.mkdir(parents=True)
    victim = tmp_path / "victim.json"
    victim.write_text("do not overwrite\n")
    (ctx.staging_dir / "study_spec.json").symlink_to(victim)

    with pytest.raises(RuntimeError, match="preexisting staged artifact"):
        rpo._step_stage_metrics(ctx)

    assert victim.read_text() == "do not overwrite\n"


def test_stage_metrics_rejects_directory_swap_before_artifact_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "results" / "runs").mkdir(parents=True)
    (tmp_path / "results" / "official_runs").mkdir(parents=True)
    _make_run(tmp_path, "r1")
    ctx = _make_ctx(tmp_path, "r1")
    external = tmp_path / "external"
    external.mkdir()
    real_write = promotion_capsule.write_new_staged_artifacts

    def swap_then_write(
        context: rpo.PromotionContext,
        artifacts: dict[str, bytes],
    ) -> None:
        context.staging_dir.mkdir(parents=True)
        displaced = tmp_path / "displaced"
        context.staging_dir.rename(displaced)
        context.staging_dir.symlink_to(external, target_is_directory=True)
        real_write(context, artifacts)

    monkeypatch.setattr(
        promotion_capsule,
        "write_new_staged_artifacts",
        swap_then_write,
    )

    with pytest.raises(RuntimeError, match="symlink"):
        rpo._step_stage_metrics(ctx)

    assert list(external.iterdir()) == []


def test_stage_charts_rejects_staging_swap_before_any_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "results" / "runs").mkdir(parents=True)
    (tmp_path / "results" / "official_runs").mkdir(parents=True)
    _make_run(tmp_path, "r1")
    ctx = _make_ctx(tmp_path, "r1")
    rpo._step_stage_metrics(ctx)
    external_run = tmp_path / "external-staging"
    external_run.mkdir(parents=True)
    (external_run / "score_analysis.json").write_text("{}")
    displaced = tmp_path / "displaced-staging"
    real_ensure = rpo._ensure_safe_staging_dir

    def validate_then_swap(
        context: rpo.PromotionContext,
        *,
        create: bool,
    ) -> Path:
        result = real_ensure(context, create=create)
        context.staging_dir.rename(displaced)
        context.staging_dir.symlink_to(
            external_run,
            target_is_directory=True,
        )
        return result

    monkeypatch.setattr(rpo, "_ensure_safe_staging_dir", validate_then_swap)
    monkeypatch.setattr(rpo, "_run_subprocess", lambda *_args: (0, "", ""))

    with pytest.raises(RuntimeError, match="symlink|staging"):
        rpo._step_stage_charts(ctx)

    assert not (external_run / "charts").exists()


def test_rollback_rejects_relocated_staging_directory(
    tmp_path: Path,
) -> None:
    (tmp_path / "results" / "runs").mkdir(parents=True)
    (tmp_path / "results" / "official_runs").mkdir(parents=True)
    _make_run(tmp_path, "r1")
    ctx = _make_ctx(tmp_path, "r1")
    rpo._step_stage_metrics(ctx)
    displaced = tmp_path / "displaced-staging"
    ctx.staging_dir.rename(displaced)
    external_run = tmp_path / "external-staging"
    external_run.mkdir(parents=True)
    victim = external_run / "victim.txt"
    victim.write_text("must survive\n")
    ctx.staging_dir.symlink_to(
        external_run,
        target_is_directory=True,
    )

    with pytest.raises(RuntimeError, match="symlink|staging"):
        rpo._rollback_staging(ctx)

    assert victim.read_text() == "must survive\n"


def test_rollback_race_quarantines_but_never_deletes_substituted_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "results" / "runs").mkdir(parents=True)
    (tmp_path / "results" / "official_runs").mkdir(parents=True)
    _make_run(tmp_path, "r1")
    ctx = _make_ctx(tmp_path, "r1")
    rpo._step_stage_metrics(ctx)
    displaced = tmp_path / "displaced-original-staging"
    victim = tmp_path / "victim-tree"
    victim.mkdir()
    marker = victim / "must-survive.txt"
    marker.write_text("must survive\n")
    real_replace = os.replace
    real_rename = os.rename

    def swap_then_replace(
        source: str,
        destination: str,
        **kwargs: object,
    ) -> None:
        real_rename(ctx.staging_dir, displaced)
        real_rename(victim, ctx.staging_dir)
        real_replace(source, destination, **kwargs)

    monkeypatch.setattr(publication_fs.os, "replace", swap_then_replace)

    with pytest.raises(RuntimeError, match="inode changed"):
        publication_fs.quarantine_staging_publication(ctx)

    quarantined = tuple(ctx.final_dir.parent.glob(".r1.discarded.*"))
    assert len(quarantined) == 1
    assert (quarantined[0] / marker.name).read_text() == "must survive\n"
    assert displaced.is_dir()


@pytest.mark.parametrize("field", ("task_hashes", "verifier_hashes"))
def test_validation_binds_receipt_provenance_to_manifest(
    tmp_path: Path,
    field: str,
) -> None:
    (tmp_path / "results" / "runs").mkdir(parents=True)
    (tmp_path / "results" / "official_runs").mkdir(parents=True)
    _make_run(tmp_path, "r1")
    ctx = _make_ctx(tmp_path, "r1")
    snapshot = rpo._capsule_snapshot(ctx)
    contract = replace(
        snapshot.analysis_contract,
        **{field: {"t1": "sha256:" + "a" * 64}},
    )
    bound = replace(snapshot, analysis_contract=contract)
    ctx = replace(ctx, capsule_snapshot=bound)

    with pytest.raises(ValueError, match=field.removesuffix("es").replace("_", " ")):
        rpo._step_validate_inputs(ctx)


def test_validation_binds_manifest_task_hash_to_current_task_bytes(
    tmp_path: Path,
) -> None:
    (tmp_path / "results" / "runs").mkdir(parents=True)
    (tmp_path / "results" / "official_runs").mkdir(parents=True)
    _make_run(tmp_path, "r1")
    task_toml = tmp_path / "benchmarks" / "suite" / "t1" / "task.toml"
    task_toml.parent.mkdir(parents=True)
    task_toml.write_text('[task]\nid = "t1"\n')
    expected_hash = file_hash(task_toml)
    ctx = _make_ctx(tmp_path, "r1")
    snapshot = rpo._capsule_snapshot(ctx)
    receipts = tuple(
        replace(receipt, task_hash=expected_hash)
        for receipt in snapshot.capsule.receipts
    )
    capsule = StudyCapsule.build(snapshot.spec, receipts)
    contract = replace(
        snapshot.analysis_contract,
        task_hashes={"t1": expected_hash},
        task_paths={"t1": "benchmarks/suite/t1/task.toml"},
    )
    bound = replace(
        snapshot,
        capsule=capsule,
        analysis_contract=contract,
    )
    ctx = replace(ctx, capsule_snapshot=bound)
    task_toml.write_text('[task]\nid = "t1"\n# drift\n')

    with pytest.raises(ValueError, match="task bytes"):
        rpo._step_validate_inputs(ctx)


def test_validation_rejects_task_hashes_without_exact_paths(tmp_path: Path) -> None:
    (tmp_path / "results" / "runs").mkdir(parents=True)
    (tmp_path / "results" / "official_runs").mkdir(parents=True)
    _make_run(tmp_path, "r1")
    task_toml = tmp_path / "benchmarks" / "suite" / "t1" / "task.toml"
    task_toml.parent.mkdir(parents=True)
    task_toml.write_text('[task]\nid = "t1"\n')
    ctx = _make_ctx(tmp_path, "r1")
    bound = _bind_task_contract(ctx, task_toml, "benchmarks/suite/t1/task.toml")
    without_paths = replace(
        bound,
        analysis_contract=replace(bound.analysis_contract, task_paths={}),
    )

    with pytest.raises(CapsuleError, match="task paths"):
        promotion_capsule.validate_declared_input_provenance(ctx, without_paths)


def test_validation_requires_exact_manifest_task_path(tmp_path: Path) -> None:
    (tmp_path / "results" / "runs").mkdir(parents=True)
    (tmp_path / "results" / "official_runs").mkdir(parents=True)
    _make_run(tmp_path, "r1")
    actual_task = tmp_path / "benchmarks" / "other" / "t1" / "task.toml"
    actual_task.parent.mkdir(parents=True)
    actual_task.write_text('[task]\nid = "t1"\n')
    ctx = _make_ctx(tmp_path, "r1")
    bound = _bind_task_contract(
        ctx,
        actual_task,
        "benchmarks/declared/t1/task.toml",
    )

    with pytest.raises(CapsuleError, match="task path"):
        promotion_capsule.validate_declared_input_provenance(ctx, bound)


def test_validation_rejects_manifest_task_symlink(tmp_path: Path) -> None:
    (tmp_path / "results" / "runs").mkdir(parents=True)
    (tmp_path / "results" / "official_runs").mkdir(parents=True)
    _make_run(tmp_path, "r1")
    target = tmp_path / "outside-task.toml"
    target.write_text('[task]\nid = "t1"\n')
    declared = tmp_path / "benchmarks" / "declared" / "t1" / "task.toml"
    declared.parent.mkdir(parents=True)
    declared.symlink_to(target)
    ctx = _make_ctx(tmp_path, "r1")
    bound = _bind_task_contract(
        ctx,
        target,
        "benchmarks/declared/t1/task.toml",
    )

    with pytest.raises(CapsuleError, match="task path"):
        promotion_capsule.validate_declared_input_provenance(ctx, bound)


def test_validation_rejects_manifest_task_hardlink(tmp_path: Path) -> None:
    (tmp_path / "results" / "runs").mkdir(parents=True)
    (tmp_path / "results" / "official_runs").mkdir(parents=True)
    _make_run(tmp_path, "r1")
    target = tmp_path / "outside-task.toml"
    target.write_text('[task]\nid = "t1"\n')
    declared = tmp_path / "benchmarks" / "declared" / "t1" / "task.toml"
    declared.parent.mkdir(parents=True)
    os.link(target, declared)
    ctx = _make_ctx(tmp_path, "r1")
    bound = _bind_task_contract(
        ctx,
        target,
        "benchmarks/declared/t1/task.toml",
    )

    with pytest.raises(CapsuleError, match="task path"):
        promotion_capsule.validate_declared_input_provenance(ctx, bound)


def test_validation_binds_task_identity_at_manifest_path(tmp_path: Path) -> None:
    (tmp_path / "results" / "runs").mkdir(parents=True)
    (tmp_path / "results" / "official_runs").mkdir(parents=True)
    _make_run(tmp_path, "r1")
    declared = tmp_path / "benchmarks" / "declared" / "t1" / "task.toml"
    declared.parent.mkdir(parents=True)
    declared.write_text('[task]\nid = "different-task"\n')
    ctx = _make_ctx(tmp_path, "r1")
    bound = _bind_task_contract(
        ctx,
        declared,
        "benchmarks/declared/t1/task.toml",
    )

    with pytest.raises(CapsuleError, match="task path identity"):
        promotion_capsule.validate_declared_input_provenance(ctx, bound)


@pytest.mark.parametrize("field", ("task_hashes", "verifier_hashes"))
def test_validation_binds_populated_invalid_receipt_provenance(
    tmp_path: Path,
    field: str,
) -> None:
    (tmp_path / "results" / "runs").mkdir(parents=True)
    (tmp_path / "results" / "official_runs").mkdir(parents=True)
    _make_run(tmp_path, "r1")
    ctx = _make_ctx(tmp_path, "r1")
    snapshot = rpo._capsule_snapshot(ctx)
    task_toml = tmp_path / "benchmarks" / "suite" / "t1" / "task.toml"
    task_toml.parent.mkdir(parents=True)
    task_toml.write_text('[task]\nid = "t1"\n')
    expected_task_hash = file_hash(task_toml)
    payload = snapshot.capsule.receipts[0].to_json()
    payload.update(
        {
            "status": "infra_invalid",
            "failure_class": "infra_timeout",
            "score": None,
            "score_contract": None,
            "task_hash": "sha256:" + "b" * 64,
            "verifier_hash": "sha256:" + "c" * 64,
        }
    )
    invalid = TrialReceipt.from_json(payload)
    capsule = replace(snapshot.capsule, receipts=(invalid,))
    contract = replace(
        snapshot.analysis_contract,
        task_hashes=({"t1": expected_task_hash} if field == "task_hashes" else {}),
        verifier_hashes=(
            {"t1": "sha256:" + "d" * 64} if field == "verifier_hashes" else {}
        ),
    )
    bound = replace(
        snapshot,
        capsule=capsule,
        analysis_contract=contract,
    )

    with pytest.raises(
        CapsuleError,
        match=field.removesuffix("es").replace("_", " "),
    ):
        promotion_capsule.validate_declared_input_provenance(
            ctx,
            bound,
        )


def test_atomic_publish_rechecks_staging_is_not_a_symlink(tmp_path: Path) -> None:
    workdir = tmp_path / "repo"
    (workdir / "results" / "runs").mkdir(parents=True)
    (workdir / "results" / "official_runs").mkdir(parents=True)
    _make_run(workdir, "r1")
    ctx = _make_ctx(workdir, "r1")
    rpo._step_stage_metrics(ctx)
    rpo._step_stage_report(ctx)
    displaced = tmp_path / "displaced-staging"
    ctx.staging_dir.rename(displaced)
    ctx.staging_dir.symlink_to(displaced, target_is_directory=True)

    with pytest.raises(RuntimeError, match="staging.*symlink"):
        rpo._step_atomic_publish(ctx)

    assert not ctx.final_dir.exists()


def test_atomic_publish_refuses_unsealed_extra_artifact(tmp_path: Path) -> None:
    workdir = tmp_path
    (workdir / "results" / "runs").mkdir(parents=True)
    (workdir / "results" / "official_runs").mkdir(parents=True)
    _make_run(workdir, "r1")
    ctx = _make_ctx(workdir, "r1")
    rpo._step_stage_metrics(ctx)
    rpo._step_stage_report(ctx)
    (ctx.staging_dir / "UNSEALED.md").write_text("must not publish\n")

    with pytest.raises(RuntimeError, match="unexpected staged artifact"):
        rpo._step_atomic_publish(ctx)

    assert not ctx.final_dir.exists()


@pytest.mark.parametrize(
    "artifact",
    (
        "study_spec.json",
        "receipts.jsonl",
        "final_manifest.json",
        "analysis_plan.json",
        "score_analysis.json",
        "report.md",
        "promotion_seal.json",
    ),
)
def test_atomic_publish_refuses_allowlisted_artifact_symlink(
    tmp_path: Path,
    artifact: str,
) -> None:
    (tmp_path / "results" / "runs").mkdir(parents=True)
    (tmp_path / "results" / "official_runs").mkdir(parents=True)
    _make_run(tmp_path, "r1")
    ctx = _make_ctx(tmp_path, "r1")
    rpo._step_stage_metrics(ctx)
    rpo._step_stage_report(ctx)
    target = ctx.staging_dir / artifact
    external = tmp_path / f"external-{artifact.replace('/', '-')}"
    external.write_bytes(target.read_bytes())
    target.unlink()
    target.symlink_to(external)

    with pytest.raises(RuntimeError, match="regular artifact|symlink"):
        rpo._step_atomic_publish(ctx)

    assert not ctx.final_dir.exists()


def test_atomic_publish_refuses_allowlisted_artifact_hardlink(tmp_path: Path) -> None:
    (tmp_path / "results" / "runs").mkdir(parents=True)
    (tmp_path / "results" / "official_runs").mkdir(parents=True)
    _make_run(tmp_path, "r1")
    ctx = _make_ctx(tmp_path, "r1")
    rpo._step_stage_metrics(ctx)
    rpo._step_stage_report(ctx)
    target = ctx.staging_dir / "report.md"
    external = tmp_path / "external-report.md"
    external.write_bytes(target.read_bytes())
    target.unlink()
    os.link(external, target)

    with pytest.raises(RuntimeError, match="single-link regular artifact"):
        rpo._step_atomic_publish(ctx)

    assert not ctx.final_dir.exists()


def test_atomic_publish_freezes_tree_before_the_final_rename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "results" / "runs").mkdir(parents=True)
    (tmp_path / "results" / "official_runs").mkdir(parents=True)
    _make_run(tmp_path, "r1")
    ctx = _make_ctx(tmp_path, "r1")
    rpo._step_stage_metrics(ctx)
    rpo._step_stage_report(ctx)
    real_rename = rpo.os.rename
    mutation_attempted = False

    def mutate_then_rename(
        source: str,
        destination: str,
        **kwargs: object,
    ) -> None:
        nonlocal mutation_attempted
        mutation_attempted = True
        (ctx.staging_dir / "report.md").write_text(
            "TOCTOU MUTATION AFTER FINAL VALIDATION\n"
        )
        real_rename(source, destination, **kwargs)

    monkeypatch.setattr(rpo.os, "rename", mutate_then_rename)

    with pytest.raises(RuntimeError, match="atomic publication rename failed"):
        rpo._step_atomic_publish(ctx)

    assert mutation_attempted
    assert not ctx.final_dir.exists()


def test_atomic_publish_revalidates_task_bytes_after_staging(tmp_path: Path) -> None:
    (tmp_path / "results" / "runs").mkdir(parents=True)
    (tmp_path / "results" / "official_runs").mkdir(parents=True)
    _make_run(tmp_path, "r1")
    task_toml = tmp_path / "benchmarks" / "suite" / "t1" / "task.toml"
    task_toml.parent.mkdir(parents=True)
    task_toml.write_text('[task]\nid = "t1"\n')
    initial = _make_ctx(tmp_path, "r1")
    ctx = replace(
        initial,
        capsule_snapshot=_bind_task_contract(
            initial,
            task_toml,
            "benchmarks/suite/t1/task.toml",
        ),
    )
    rpo._step_stage_metrics(ctx)
    rpo._step_stage_report(ctx)
    task_toml.write_text('[task]\nid = "t1"\n# changed after staging\n')

    with pytest.raises(CapsuleError, match="task bytes"):
        rpo._step_atomic_publish(ctx)

    assert not ctx.final_dir.exists()


def test_atomic_publish_rejects_whole_staging_tree_substitution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "results" / "runs").mkdir(parents=True)
    (tmp_path / "results" / "official_runs").mkdir(parents=True)
    _make_run(tmp_path, "r1")
    ctx = _make_ctx(tmp_path, "r1")
    rpo._step_stage_metrics(ctx)
    rpo._step_stage_report(ctx)
    replacement = tmp_path / "replacement-staging"
    shutil.copytree(ctx.staging_dir, replacement)
    displaced = tmp_path / "displaced-staging"
    real_rename = rpo.os.rename

    def substitute_then_rename(
        source: str,
        destination: str,
        **kwargs: object,
    ) -> None:
        real_rename(ctx.staging_dir, displaced)
        real_rename(replacement, ctx.staging_dir)
        real_rename(source, destination, **kwargs)

    monkeypatch.setattr(rpo.os, "rename", substitute_then_rename)

    with pytest.raises(RuntimeError, match="atomic publication rename failed"):
        rpo._step_atomic_publish(ctx)

    assert not ctx.final_dir.exists()


def test_atomic_publish_rejects_final_tree_substitution_after_rename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "results" / "runs").mkdir(parents=True)
    (tmp_path / "results" / "official_runs").mkdir(parents=True)
    _make_run(tmp_path, "r1")
    ctx = _make_ctx(tmp_path, "r1")
    rpo._step_stage_metrics(ctx)
    rpo._step_stage_report(ctx)
    replacement = ctx.final_dir.parent / ".replacement-final"
    shutil.copytree(ctx.staging_dir, replacement)
    for path in replacement.iterdir():
        path.chmod(0o444)
    replacement.chmod(0o555)
    displaced = ctx.final_dir.parent / ".displaced-frozen-final"
    real_validate = rpo._validate_final_publication

    def substitute_then_validate(
        context: rpo.PromotionContext,
        snapshot: rpo.CapsuleSnapshot,
        frozen_identity: tuple[int, int],
    ) -> None:
        context.final_dir.rename(displaced)
        replacement.rename(context.final_dir)
        real_validate(context, snapshot, frozen_identity)

    monkeypatch.setattr(
        rpo,
        "_validate_final_publication",
        substitute_then_validate,
    )

    with pytest.raises(RuntimeError, match="inode"):
        rpo._step_atomic_publish(ctx)

    assert not ctx.final_dir.exists()


def test_failed_final_validation_cannot_leave_official_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "results" / "runs").mkdir(parents=True)
    (tmp_path / "results" / "official_runs").mkdir(parents=True)
    _make_run(tmp_path, "r1")
    ctx = _make_ctx(tmp_path, "r1")
    rpo._step_stage_metrics(ctx)
    rpo._step_stage_report(ctx)

    def fail_with_staging_collision(
        _ctx: rpo.PromotionContext,
        _snapshot: rpo.CapsuleSnapshot,
        _frozen_identity: tuple[int, int],
    ) -> None:
        ctx.staging_dir.mkdir()
        raise RuntimeError("forced final validation failure")

    monkeypatch.setattr(
        rpo,
        "_validate_final_publication",
        fail_with_staging_collision,
    )

    with pytest.raises(RuntimeError, match="forced final validation failure"):
        rpo._step_atomic_publish(ctx)

    assert not ctx.final_dir.exists()


def test_frozen_staging_rejects_directory_entry_replacement(tmp_path: Path) -> None:
    (tmp_path / "results" / "runs").mkdir(parents=True)
    (tmp_path / "results" / "official_runs").mkdir(parents=True)
    _make_run(tmp_path, "r1")
    ctx = _make_ctx(tmp_path, "r1")
    rpo._step_stage_metrics(ctx)
    rpo._step_stage_report(ctx)
    replacement = ctx.staging_dir.parent / ".replacement"
    replacement.write_text("must not replace a frozen artifact\n")

    rpo._freeze_staged_publication(ctx, rpo.PUBLICATION_FILES)
    try:
        assert ctx.staging_dir.stat().st_mode & 0o777 == 0o555
        with pytest.raises(PermissionError):
            os.replace(replacement, ctx.staging_dir / "report.md")
    finally:
        rpo._thaw_publication(ctx, location="staging")


def test_stage_metrics_rejects_secret_shaped_study_text(tmp_path: Path) -> None:
    (tmp_path / "results" / "runs").mkdir(parents=True)
    (tmp_path / "results" / "official_runs").mkdir(parents=True)
    _make_run(tmp_path, "r1")
    ctx = _make_ctx(tmp_path, "r1")
    payload = json.loads(ctx.spec_path.read_text())
    payload["model"] = "sk-proj-SECRET-SENTINEL-123456789"
    ctx.spec_path.write_text(json.dumps(payload))

    with pytest.raises(CapsuleError, match="secret"):
        rpo._step_stage_metrics(ctx)

    assert not (ctx.staging_dir / "score_analysis.json").exists()


def test_stage_report_refuses_analyzer_mutated_after_metrics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "results" / "runs").mkdir(parents=True)
    (tmp_path / "results" / "official_runs").mkdir(parents=True)
    _make_run(tmp_path, "r1")
    analyzer = _fake_analysis_tools(tmp_path, monkeypatch)
    initial = _make_ctx(tmp_path, "r1", study_report_path=analyzer)
    ctx = replace(initial, capsule_snapshot=rpo._capsule_snapshot(initial))
    rpo._step_stage_metrics(ctx)
    analyzer.write_text("# analyzer v2 injected after metrics\n")

    with pytest.raises(RuntimeError, match="analysis tool changed"):
        rpo._step_stage_report(ctx)


def test_atomic_publish_refuses_renderer_mutated_after_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "results" / "runs").mkdir(parents=True)
    (tmp_path / "results" / "official_runs").mkdir(parents=True)
    _make_run(tmp_path, "r1")
    analyzer = _fake_analysis_tools(tmp_path, monkeypatch)
    initial = _make_ctx(tmp_path, "r1", study_report_path=analyzer)
    ctx = replace(initial, capsule_snapshot=rpo._capsule_snapshot(initial))
    rpo._step_stage_metrics(ctx)
    rpo._step_stage_report(ctx)
    analyzer.with_name("study_markdown_report.py").write_text(
        "# renderer v2 injected after report\n"
    )

    with pytest.raises(RuntimeError, match="analysis tool changed"):
        rpo._step_atomic_publish(ctx)
