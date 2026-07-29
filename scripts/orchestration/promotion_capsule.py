"""Named-capsule validation and staging for benchmark promotion."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_ROOT))

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

from eb_study import (  # noqa: E402
    CapsuleError,
    ReceiptError,
    SpecError,
    StudyCapsule,
    StudySpec,
    TrialReceipt,
    strict_json_loads,
)
from eb_verify.redact import redact  # noqa: E402
from analysis.study_inference import (  # noqa: E402
    AnalysisContract,
    parse_analysis_contract,
)
from analysis.study_markdown_report import render_markdown  # noqa: E402
from analysis.study_report import build_report  # noqa: E402

if __package__:
    from .publication_fs import (
        ensure_staging_directory,
        read_publication_artifact,
        read_trusted_repository_file,
        remove_staged_artifact,
        validate_publication_inventory,
        write_new_staged_artifacts,
        write_staged_artifact,
    )
    from .promotion_types import CapsuleSnapshot, PromotionContext, StepOutcome
else:
    from publication_fs import (
        ensure_staging_directory,
        read_publication_artifact,
        read_trusted_repository_file,
        remove_staged_artifact,
        validate_publication_inventory,
        write_new_staged_artifacts,
        write_staged_artifact,
    )
    from promotion_types import CapsuleSnapshot, PromotionContext, StepOutcome

PUBLICATION_FILES = frozenset(
    {
        "study_spec.json",
        "receipts.jsonl",
        "final_manifest.json",
        "analysis_plan.json",
        "score_analysis.json",
        "report.md",
        "promotion_seal.json",
    }
)
ANALYSIS_FIELDS = frozenset(
    {
        "schema_version",
        "generated_at",
        "analysis",
        "provenance",
        "completeness",
        "reward",
        "economics",
        "tokens",
        "timing",
    }
)


def validate_staged_publication(ctx: PromotionContext) -> None:
    """Require the exact sealed artifact inventory before atomic rename."""

    ensure_staging_directory(ctx, create=False)
    remove_staged_artifact(ctx, "_progress.json")
    validate_publication_inventory(ctx, PUBLICATION_FILES)


def validate_inputs(ctx: PromotionContext) -> StepOutcome:
    """Validate the exact named Study Capsule that promotion will consume."""

    if not ctx.raw_run_dir.is_dir():
        raise FileNotFoundError(f"Raw run directory not found: {ctx.raw_run_dir}")

    try:
        snapshot = capsule_snapshot(ctx)
        spec = snapshot.spec
    except CapsuleError as exc:
        raise ValueError(f"invalid study capsule: {exc}") from exc

    try:
        capsule = snapshot.capsule
        paired = capsule.paired_valid()
        validate_declared_input_provenance(ctx, snapshot)
    except CapsuleError as exc:
        raise ValueError(f"study capsule is incomplete or invalid: {exc}") from exc
    if paired.excluded:
        raise ValueError(
            f"study capsule is incomplete: {len(paired.excluded)} declared "
            "task(s) are missing one or more arm/repetition slots"
        )

    return StepOutcome(
        step_name="validate_inputs",
        status="reversible",
        details=(
            f"study_id={spec.study_id} spec_hash={spec.spec_hash} "
            f"receipts={len(capsule.receipts)}"
        ),
    )


def capsule_snapshot(ctx: PromotionContext) -> CapsuleSnapshot:
    """Read and validate one immutable in-memory snapshot of the named capsule."""

    if ctx.capsule_snapshot is not None:
        return ctx.capsule_snapshot

    try:
        spec_source = ctx.spec_path.read_bytes()
    except OSError as exc:
        raise SpecError(f"cannot read study spec {ctx.spec_path}: {exc}") from exc
    try:
        receipts_source = ctx.receipts_path.read_bytes()
    except OSError as exc:
        raise ReceiptError(f"cannot read receipts {ctx.receipts_path}: {exc}") from exc
    try:
        task_manifest_source = ctx.task_manifest_path.read_bytes()
        analysis_plan_source = ctx.analysis_plan_path.read_bytes()
    except OSError as exc:
        raise CapsuleError(f"cannot read analysis contract input: {exc}") from exc
    markdown_report_path = ctx.study_report_path.with_name("study_markdown_report.py")
    try:
        study_report_source = ctx.study_report_path.read_bytes()
        markdown_report_source = markdown_report_path.read_bytes()
    except OSError as exc:
        raise CapsuleError(f"cannot read publication analysis tool: {exc}") from exc

    for label, source in (
        ("study spec", spec_source),
        ("receipts", receipts_source),
        ("task manifest", task_manifest_source),
        ("analysis plan", analysis_plan_source),
    ):
        _reject_secret_source(label, source)

    try:
        spec_payload = strict_json_loads(spec_source.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise SpecError(f"study spec {ctx.spec_path} is not valid JSON: {exc}") from exc
    spec = StudySpec.from_json(spec_payload)
    if spec.study_id != ctx.run_id:
        raise SpecError(
            f"study_id {spec.study_id!r} does not match promoted run {ctx.run_id!r}"
        )

    receipts: list[TrialReceipt] = []
    try:
        receipts_text = receipts_source.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReceiptError(f"receipts {ctx.receipts_path} are not UTF-8") from exc
    for lineno, line in enumerate(receipts_text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = strict_json_loads(line)
        except ValueError as exc:
            raise ReceiptError(
                f"{ctx.receipts_path}:{lineno} is not valid JSON: {exc}"
            ) from exc
        try:
            receipts.append(TrialReceipt.from_json(payload))
        except ReceiptError as exc:
            raise ReceiptError(f"{ctx.receipts_path}:{lineno}: {exc}") from exc

    capsule = StudyCapsule.build(spec, receipts)
    analysis_contract = parse_analysis_contract(
        spec,
        analysis_plan_source,
        task_manifest_source,
    )
    return CapsuleSnapshot(
        spec_source=spec_source,
        receipts_source=receipts_source,
        task_manifest_source=task_manifest_source,
        analysis_plan_source=analysis_plan_source,
        study_report_source=study_report_source,
        markdown_report_source=markdown_report_source,
        spec=spec,
        capsule=capsule,
        analysis_contract=analysis_contract,
    )


def _reject_secret_source(label: str, source: bytes) -> None:
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError:
        return
    if redact(text) != text:
        raise CapsuleError(f"{label} contains secret-shaped text")


def assert_capsule_source_unchanged(
    ctx: PromotionContext, snapshot: CapsuleSnapshot
) -> None:
    """Fail if the raw capsule changed after its validation snapshot."""

    try:
        current_spec = ctx.spec_path.read_bytes()
        current_receipts = ctx.receipts_path.read_bytes()
        current_manifest = ctx.task_manifest_path.read_bytes()
        current_plan = ctx.analysis_plan_path.read_bytes()
    except OSError as exc:
        raise RuntimeError(f"capsule changed after validation: {exc}") from exc
    if (
        current_spec != snapshot.spec_source
        or current_receipts != snapshot.receipts_source
        or current_manifest != snapshot.task_manifest_source
        or current_plan != snapshot.analysis_plan_source
    ):
        raise RuntimeError("capsule changed after validation")


def assert_analysis_tools_unchanged(
    ctx: PromotionContext, snapshot: CapsuleSnapshot
) -> None:
    """Fail if either executable changed after the promotion snapshot."""

    try:
        current_analyzer = ctx.study_report_path.read_bytes()
        current_renderer = ctx.study_report_path.with_name(
            "study_markdown_report.py"
        ).read_bytes()
    except OSError as exc:
        raise RuntimeError(f"analysis tool changed after validation: {exc}") from exc
    if (
        current_analyzer != snapshot.study_report_source
        or current_renderer != snapshot.markdown_report_source
    ):
        raise RuntimeError("analysis tool changed after validation")


def declared_task_tomls(ctx: PromotionContext) -> tuple[Path, ...]:
    """Resolve every spec task ID to exactly one benchmark task.toml."""

    spec = capsule_snapshot(ctx).spec
    expected = set(spec.task_ids)
    matches: dict[str, list[Path]] = {task_id: [] for task_id in spec.task_ids}
    for path in (ctx.repo_root / "benchmarks").rglob("task.toml"):
        try:
            with path.open("rb") as handle:
                task_id = tomllib.load(handle).get("task", {}).get("id")
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise RuntimeError(
                f"cannot read declared task candidate {path}: {exc}"
            ) from exc
        if task_id in expected:
            matches[task_id].append(path)

    invalid = {task_id: paths for task_id, paths in matches.items() if len(paths) != 1}
    if invalid:
        detail = ", ".join(
            f"{task_id}={len(paths)} matches" for task_id, paths in invalid.items()
        )
        raise RuntimeError(f"declared task resolution failed: {detail}")
    return tuple(matches[task_id][0] for task_id in spec.task_ids)


def stage_metrics(
    ctx: PromotionContext,
) -> StepOutcome:
    """Build the validated named capsule's report into staging."""

    if ctx.dry_run:
        return StepOutcome(
            step_name="stage_metrics",
            status="dry_run",
            details="would aggregate metrics into staging",
        )

    snapshot = capsule_snapshot(ctx)
    assert_capsule_source_unchanged(ctx, snapshot)
    assert_analysis_tools_unchanged(ctx, snapshot)
    validate_declared_input_provenance(ctx, snapshot)
    report_source = _build_report_source(snapshot)
    write_new_staged_artifacts(ctx, _staged_sources(snapshot, report_source))
    assert_analysis_tools_unchanged(ctx, snapshot)

    paired_tasks, _analysis = validate_staged_study_analysis(
        ctx,
        snapshot.spec,
        snapshot.analysis_contract,
    )
    seal_path = write_promotion_seal(ctx, snapshot)
    artifact_names = (
        "score_analysis.json",
        "study_spec.json",
        "receipts.jsonl",
        "final_manifest.json",
        "analysis_plan.json",
    )
    return StepOutcome(
        step_name="stage_metrics",
        status="reversible",
        details=f"wrote score_analysis.json ({paired_tasks} paired tasks)",
        artifacts=tuple(
            str(ctx.staging_dir / name) for name in (*artifact_names, seal_path.name)
        ),
    )


def _build_report_source(snapshot: CapsuleSnapshot) -> bytes:
    """Build canonical report bytes from one immutable snapshot."""

    report = build_report(
        snapshot.capsule,
        contract=snapshot.analysis_contract,
        source_hashes={
            "study_spec_file_hash": _bytes_hash(snapshot.spec_source),
            "receipts_file_hash": _bytes_hash(snapshot.receipts_source),
        },
    )
    try:
        report_source = (
            json.dumps(
                report,
                indent=2,
                allow_nan=False,
            )
            + "\n"
        ).encode()
    except ValueError as exc:
        raise RuntimeError("study report contains a non-finite number") from exc
    _reject_secret_source("study report", report_source)
    return report_source


def _staged_sources(
    snapshot: CapsuleSnapshot,
    report_source: bytes,
) -> dict[str, bytes]:
    return {
        "study_spec.json": snapshot.spec_source,
        "receipts.jsonl": snapshot.receipts_source,
        "final_manifest.json": snapshot.task_manifest_source,
        "analysis_plan.json": snapshot.analysis_plan_source,
        "score_analysis.json": report_source,
    }


def validate_declared_input_provenance(
    ctx: PromotionContext,
    snapshot: CapsuleSnapshot,
) -> None:
    """Bind valid receipts and current task bytes to the locked manifest."""

    contract = snapshot.analysis_contract
    _validate_receipt_provenance(snapshot, contract)
    _validate_declared_task_files(ctx, contract)


def _validate_receipt_provenance(
    snapshot: CapsuleSnapshot,
    contract: AnalysisContract,
) -> None:
    for receipt in snapshot.capsule.receipts:
        task_id = receipt.trial.task_id
        expected_task_hash = contract.task_hashes.get(task_id)
        expected_verifier_hash = contract.verifier_hashes.get(task_id)
        if (
            expected_task_hash is not None
            and (receipt.is_valid or receipt.task_hash is not None)
            and receipt.task_hash != expected_task_hash
        ):
            raise CapsuleError(
                f"receipt task hash does not match manifest for {task_id}"
            )
        if (
            expected_verifier_hash is not None
            and (receipt.is_valid or receipt.verifier_hash is not None)
            and receipt.verifier_hash != expected_verifier_hash
        ):
            raise CapsuleError(
                f"receipt verifier hash does not match manifest for {task_id}"
            )


def _validate_declared_task_files(
    ctx: PromotionContext,
    contract: AnalysisContract,
) -> None:
    if not contract.task_hashes:
        return
    if set(contract.task_paths) != set(contract.task_hashes):
        raise CapsuleError("task paths do not match manifest task hashes")
    for task_id, expected in contract.task_hashes.items():
        _validate_exact_declared_task(
            ctx,
            task_id,
            contract.task_paths[task_id],
            expected,
        )


def _validate_exact_declared_task(
    ctx: PromotionContext,
    task_id: str,
    relative_path: str,
    expected_hash: str,
) -> None:
    try:
        source = read_trusted_repository_file(ctx.repo_root, relative_path)
    except RuntimeError as exc:
        raise CapsuleError(f"task path is not safely readable for {task_id}") from exc
    try:
        payload = tomllib.loads(source.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise CapsuleError(f"task path is not valid TOML for {task_id}") from exc
    task = payload.get("task")
    if not isinstance(task, dict) or task.get("id") != task_id:
        raise CapsuleError(f"task path identity does not match manifest for {task_id}")
    if _bytes_hash(source) != expected_hash:
        raise CapsuleError(f"task bytes do not match manifest for {task_id}")


def validate_staged_study_analysis(
    ctx: PromotionContext,
    spec: StudySpec,
    contract: AnalysisContract,
    *,
    location: str = "staging",
) -> tuple[int, dict[str, object]]:
    """Validate analysis and its inputs through descriptor-safe reads."""

    try:
        analysis_source = read_publication_artifact(
            ctx,
            "score_analysis.json",
            location=location,
        )
        analysis = strict_json_loads(analysis_source.decode())
    except (UnicodeDecodeError, ValueError) as exc:
        raise RuntimeError("staged analysis is unreadable") from exc
    if not isinstance(analysis, dict):
        raise RuntimeError("staged analysis is unreadable")
    source_hashes = {
        "study_spec_file_hash": _bytes_hash(
            read_publication_artifact(
                ctx,
                "study_spec.json",
                location=location,
            )
        ),
        "receipts_file_hash": _bytes_hash(
            read_publication_artifact(
                ctx,
                "receipts.jsonl",
                location=location,
            )
        ),
    }
    paired_tasks = _validate_study_analysis_payload(
        analysis, spec, contract, source_hashes
    )
    return paired_tasks, analysis


def stage_markdown_report(
    ctx: PromotionContext,
    snapshot: CapsuleSnapshot,
    *,
    console_url: str,
) -> Path:
    """Render and seal Markdown without giving a subprocess a mutable path."""

    assert_analysis_tools_unchanged(ctx, snapshot)
    _paired_tasks, analysis = validate_staged_study_analysis(
        ctx,
        snapshot.spec,
        snapshot.analysis_contract,
    )
    report = render_markdown(analysis, console_url=console_url).encode()
    write_staged_artifact(
        ctx,
        "report.md",
        report,
        replace=False,
    )
    assert_analysis_tools_unchanged(ctx, snapshot)
    write_promotion_seal(ctx, snapshot)
    return ctx.staging_dir / "report.md"


def _validate_study_analysis_payload(
    analysis: dict[str, object],
    spec: StudySpec,
    contract: AnalysisContract,
    source_hashes: dict[str, str],
) -> int:
    """Verify one parsed report against the frozen contract and sources."""

    provenance, completeness = _validate_analysis_envelope(analysis)
    _validate_analysis_provenance(provenance, spec, contract, source_hashes)
    return _validate_analysis_completeness(completeness)


def _validate_analysis_envelope(
    analysis: dict[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    unknown = sorted(set(analysis) - ANALYSIS_FIELDS)
    if unknown:
        raise RuntimeError(
            f"staged analysis contains unknown field(s): {', '.join(unknown)}"
        )
    provenance = analysis.get("provenance")
    completeness = analysis.get("completeness")
    if not isinstance(provenance, dict) or not isinstance(completeness, dict):
        raise RuntimeError(
            "staged analysis is unreadable: missing provenance/completeness"
        )
    if analysis.get("schema_version") != 3:
        raise RuntimeError("staged analysis uses an unsupported schema")
    analysis_status = analysis.get("analysis")
    if (
        not isinstance(analysis_status, dict)
        or analysis_status.get("status") != "complete"
    ):
        raise RuntimeError("staged analysis withheld confirmatory inference")
    return provenance, completeness


def _validate_analysis_provenance(
    provenance: dict[str, object],
    spec: StudySpec,
    contract: AnalysisContract,
    source_hashes: dict[str, str],
) -> None:
    if provenance.get("study_id") != spec.study_id:
        raise RuntimeError(
            f"staged analysis study_id={provenance.get('study_id')!r}, "
            f"expected {spec.study_id!r}"
        )
    if provenance.get("spec_hash") != spec.spec_hash:
        raise RuntimeError(
            f"staged analysis spec_hash={provenance.get('spec_hash')!r}, "
            f"expected {spec.spec_hash!r}"
        )
    plan_hash = contract.plan_hash
    manifest_hash = contract.manifest_hash
    if provenance.get("analysis_plan_hash") != plan_hash:
        raise RuntimeError("staged analysis names the wrong analysis plan")
    if provenance.get("task_manifest_hash") != manifest_hash:
        raise RuntimeError("staged analysis names the wrong task manifest")
    if any(provenance.get(key) != expected for key, expected in source_hashes.items()):
        raise RuntimeError("staged analysis source hashes do not match staged inputs")
    expected_contract_provenance = {
        "candidate_manifest_hash": contract.candidate_manifest_hash,
        "candidate_lock_revision": contract.candidate_lock_revision,
        "execution_order_hash": contract.execution_order_hash,
        "execution_order_count": contract.execution_order_count,
        "agent_account": contract.agent_account,
        "judge_account": contract.judge_account,
        "task_type_counts": dict(contract.stratum_counts),
    }
    if any(
        provenance.get(key) != expected
        for key, expected in expected_contract_provenance.items()
    ):
        raise RuntimeError("staged analysis contract provenance does not match")


def _validate_analysis_completeness(completeness: dict[str, object]) -> int:
    paired = completeness.get("paired_tasks")
    declared = completeness.get("declared_tasks")
    excluded = completeness.get("excluded_tasks")
    if not isinstance(paired, int) or paired < 1:
        raise RuntimeError("staged analysis has no paired tasks")
    if paired != declared or excluded:
        raise RuntimeError(
            "staged analysis is incomplete: paired_tasks must equal "
            "declared_tasks and excluded_tasks must be empty"
        )
    return paired


def write_promotion_seal(
    ctx: PromotionContext,
    snapshot: CapsuleSnapshot,
) -> Path:
    """Write a digest manifest for every currently staged publication artifact."""

    ensure_staging_directory(ctx, create=False)
    seal_path = ctx.staging_dir / "promotion_seal.json"
    source = (
        json.dumps(
            _promotion_seal_payload(ctx, snapshot, location="staging"),
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode()
    write_staged_artifact(
        ctx,
        "promotion_seal.json",
        source,
        replace=True,
    )
    return seal_path


def validate_promotion_seal(
    ctx: PromotionContext,
    snapshot: CapsuleSnapshot,
    *,
    location: str = "staging",
) -> None:
    """Recompute every staged digest immediately before atomic publication."""

    try:
        sealed = strict_json_loads(
            read_publication_artifact(
                ctx,
                "promotion_seal.json",
                location=location,
            ).decode()
        )
    except (UnicodeDecodeError, ValueError) as exc:
        raise RuntimeError(f"promotion seal is unreadable: {exc}") from exc
    expected = _promotion_seal_payload(ctx, snapshot, location=location)
    if sealed != expected:
        raise RuntimeError("promotion seal does not match staged artifacts")


def _promotion_seal_payload(
    ctx: PromotionContext,
    snapshot: CapsuleSnapshot,
    *,
    location: str,
) -> dict[str, object]:
    files = [
        "study_spec.json",
        "receipts.jsonl",
        "final_manifest.json",
        "analysis_plan.json",
        "score_analysis.json",
    ]
    try:
        read_publication_artifact(ctx, "report.md", location=location)
    except RuntimeError:
        pass
    else:
        files.append("report.md")
    try:
        file_hashes = {
            name: _bytes_hash(read_publication_artifact(ctx, name, location=location))
            for name in files
        }
    except RuntimeError as exc:
        raise RuntimeError(f"promotion seal input is unreadable: {exc}") from exc
    payload: dict[str, object] = {
        "schema_version": 1,
        "study_id": snapshot.spec.study_id,
        "spec_hash": snapshot.spec.spec_hash,
        "analysis_plan_hash": snapshot.analysis_contract.plan_hash,
        "task_manifest_hash": snapshot.analysis_contract.manifest_hash,
        "analyzer_hash": _bytes_hash(snapshot.study_report_source),
        "report_renderer_hash": _bytes_hash(snapshot.markdown_report_source),
        "files": file_hashes,
    }
    return payload


def _bytes_hash(source: bytes) -> str:
    return f"sha256:{hashlib.sha256(source).hexdigest()}"
