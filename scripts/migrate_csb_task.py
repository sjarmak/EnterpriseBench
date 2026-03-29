#!/usr/bin/env python3
"""Migrate CodeScaleBench tasks to EnterpriseBench format.

Usage:
    python scripts/migrate_csb_task.py <csb_task_dir> [--output <dir>] [--validate]
    python scripts/migrate_csb_task.py --batch <csb_suite_dir> [--limit N] [--output <dir>]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

# ---------------------------------------------------------------------------
# CSB suite → EB cluster mapping (from docs/taxonomy_mapping.md)
# ---------------------------------------------------------------------------
SUITE_TO_CLUSTER: dict[str, str] = {
    "csb_org_compliance": "security_operations",
    "csb_org_crossorg": "customer_escalation",
    "csb_org_crossrepo": "dependency_management",
    "csb_org_crossrepo_tracing": "dependency_management",
    "csb_org_domain": "feature_delivery",
    "csb_org_incident": "incident_response",
    "csb_org_migration": "technical_debt",
    "csb_org_onboarding": "customer_escalation",
    "csb_org_org": "feature_delivery",
    "csb_org_platform": "platform_engineering",
    "csb_org_security": "security_operations",
    "csb_sdlc_debug": "incident_response",
    "csb_sdlc_design": "feature_delivery",
    "csb_sdlc_document": "feature_delivery",
    "csb_sdlc_feature": "feature_delivery",
    "csb_sdlc_fix": "incident_response",
    "csb_sdlc_refactor": "technical_debt",
    "csb_sdlc_secure": "security_operations",
    "csb_sdlc_test": "feature_delivery",
    "csb_sdlc_understand": "customer_escalation",
}

# Legacy subcategory → EB cluster (for tasks without csb_ origin_suite)
SUBCATEGORY_TO_CLUSTER: dict[str, str] = {
    "debug": "incident_response",
    "document": "feature_delivery",
    "fix": "incident_response",
    "refactor": "technical_debt",
    "security": "security_operations",
    "understand": "customer_escalation",
    "feature": "feature_delivery",
    "crossrepo": "dependency_management",
}

# CSB task type categories → artifact types
VERIFICATION_TO_ARTIFACTS: dict[str, list[str]] = {
    "artifact": ["answer"],
    "test_ratio": ["code_patch"],
    "checklist": ["code_patch"],
    "find_and_prove": ["code_patch"],
    "score": ["answer"],
}

# Difficulty mapping (CSB only uses "hard" generally)
DIFFICULTY_MAP: dict[str, str] = {
    "easy": "medium",
    "medium": "medium",
    "hard": "hard",
    "expert": "expert",
}

# CSB root
CSB_ROOT = Path.home() / "CodeScaleBench"
CANONICAL_PATH = CSB_ROOT / "benchmarks" / "CANONICAL.json"


@dataclass
class MigrationWarning:
    field: str
    message: str


@dataclass
class MigrationResult:
    task_id: str
    success: bool
    output_path: str | None = None
    warnings: list[MigrationWarning] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)


def _load_canonical() -> dict[str, dict[str, Any]]:
    """Load CANONICAL.json and index by lowercase task ID."""
    if not CANONICAL_PATH.exists():
        return {}
    with open(CANONICAL_PATH) as f:
        data = json.load(f)
    tasks = data.get("categories", {}).get("base", [])
    index: dict[str, dict[str, Any]] = {}
    for t in tasks:
        tid = t.get("id", "").lower()
        if tid:
            index[tid] = t
    return index


def _read_json(path: Path) -> dict[str, Any] | None:
    """Read a JSON file, returning None if it doesn't exist."""
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _read_toml(path: Path) -> dict[str, Any] | None:
    """Read a TOML file, returning None if it doesn't exist."""
    if not path.exists():
        return None
    with open(path, "rb") as f:
        return tomllib.load(f)


def _read_text(path: Path) -> str | None:
    """Read a text file, returning None if it doesn't exist."""
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def _normalize_id(raw_id: str) -> str:
    """Normalize a CSB task ID to EB format: lowercase, alphanumeric + hyphens.

    EB pattern: ^[a-z][a-z0-9-]+-\\d{3}$
    """
    normalized = raw_id.lower().strip()
    # Already has trailing digits? Keep as-is (after cleanup)
    # Replace underscores with hyphens
    normalized = normalized.replace("_", "-")
    # Remove any chars that aren't lowercase alpha, digits, or hyphens
    normalized = re.sub(r"[^a-z0-9-]", "", normalized)
    # Collapse multiple hyphens
    normalized = re.sub(r"-{2,}", "-", normalized)
    # Strip leading/trailing hyphens
    normalized = normalized.strip("-")
    # Ensure it matches the pattern: ends with -NNN
    if not re.search(r"-\d{3}$", normalized):
        # Try to find trailing digits
        match = re.search(r"-(\d+)$", normalized)
        if match:
            num = match.group(1)
            normalized = normalized[: match.start()] + f"-{int(num):03d}"
        else:
            # No number found, append -001
            normalized = normalized + "-001"
    return normalized


def _parse_repo_field(repo_str: str) -> dict[str, Any]:
    """Parse CSB repo field like 'sg-evals/envoy--v1.31.2' into EB repo dict."""
    # Format: "sg-evals/repo--version" or "org/repo"
    repo_info: dict[str, Any] = {
        "url": "",
        "rev": "HEAD",
        "path": "",
        "role": "primary",
    }

    if not repo_str:
        return repo_info

    # sg-evals format: sg-evals/name--version
    sg_match = re.match(r"sg-evals/(.+?)--(.+)$", repo_str)
    if sg_match:
        repo_name = sg_match.group(1)
        version = sg_match.group(2)
        repo_info["url"] = f"github.com/sg-evals/{repo_name}"
        repo_info["rev"] = version
        repo_info["path"] = repo_name
        return repo_info

    # Standard format: org/repo
    if "/" in repo_str:
        parts = repo_str.split("/")
        repo_name = parts[-1]
        repo_info["url"] = f"github.com/{repo_str}"
        repo_info["path"] = repo_name
    else:
        repo_info["url"] = f"github.com/{repo_str}"
        repo_info["path"] = repo_str

    return repo_info


def _determine_suite(
    csb_task_dir: Path,
    canonical_entry: dict[str, Any] | None,
    warnings: list[MigrationWarning],
) -> str:
    """Determine the EB suite from CSB origin_suite or directory name."""
    # Try canonical entry first
    if canonical_entry:
        origin_suite = canonical_entry.get("metadata", {}).get("origin_suite", "")
        if origin_suite and origin_suite in SUITE_TO_CLUSTER:
            return SUITE_TO_CLUSTER[origin_suite]
        # Try subcategory for legacy tasks
        subcategory = canonical_entry.get("subcategory", "")
        if subcategory and subcategory in SUBCATEGORY_TO_CLUSTER:
            return SUBCATEGORY_TO_CLUSTER[subcategory]

    # Infer from directory path
    parent_name = csb_task_dir.parent.name
    if parent_name in SUITE_TO_CLUSTER:
        return SUITE_TO_CLUSTER[parent_name]

    warnings.append(MigrationWarning(
        field="task.suite",
        message=f"Could not determine suite from '{parent_name}', defaulting to 'feature_delivery'",
    ))
    return "feature_delivery"


def _determine_artifacts(
    csb_task: dict[str, Any],
    canonical_entry: dict[str, Any] | None,
) -> list[str]:
    """Determine required artifacts from verification_modes or reward_type."""
    # Check verification_modes from task.toml
    verification_modes = csb_task.get("task", {}).get("verification_modes", [])
    if verification_modes:
        first_mode = verification_modes[0] if isinstance(verification_modes, list) else verification_modes
        if first_mode in VERIFICATION_TO_ARTIFACTS:
            return VERIFICATION_TO_ARTIFACTS[first_mode]

    # Check reward_type from verification section
    reward_type = csb_task.get("verification", {}).get("reward_type", "")
    if reward_type in VERIFICATION_TO_ARTIFACTS:
        return VERIFICATION_TO_ARTIFACTS[reward_type]

    # Check canonical
    if canonical_entry:
        modes = canonical_entry.get("task", {}).get("verification_modes", [])
        if modes:
            first_mode = modes[0] if isinstance(modes, list) else modes
            if first_mode in VERIFICATION_TO_ARTIFACTS:
                return VERIFICATION_TO_ARTIFACTS[first_mode]

    return ["answer"]


def _determine_gt_tiers(gt_meta: dict[str, Any] | None) -> list[str]:
    """Determine ground truth tiers from ground_truth_meta.json."""
    if not gt_meta:
        return ["curator"]
    source = gt_meta.get("ground_truth_source", "")
    if "deterministic" in source:
        return ["deterministic"]
    if "curator" in source:
        return ["curator"]
    return ["curator"]


def _determine_stratum(
    repo_count: int,
    csb_task: dict[str, Any],
    canonical_entry: dict[str, Any] | None,
) -> str:
    """Determine difficulty_stratum based on repo count and task properties."""
    org_scale = csb_task.get("task", {}).get("org_scale", False)
    if canonical_entry:
        org_scale = org_scale or canonical_entry.get("task", {}).get("org_scale", False)

    if repo_count >= 3:
        return "multi_repo"
    if repo_count == 2:
        return "dual_repo"

    # Single repo
    time_limit = csb_task.get("task", {}).get("time_limit_sec", 900)
    if time_limit <= 600 and not org_scale:
        return "calibration"
    return "large_single"


def _build_ground_truth_files(
    gt_json: dict[str, Any] | None,
    task_spec: dict[str, Any] | None,
    repo_path: str,
) -> list[dict[str, Any]]:
    """Extract required_files from ground_truth.json for the EB schema."""
    required_files: list[dict[str, Any]] = []
    if not gt_json:
        return required_files

    files_list = gt_json.get("files", [])
    for f in files_list[:10]:  # Limit to 10 files
        if isinstance(f, str):
            # Format: "repo::path" or just "path"
            if "::" in f:
                _repo, fpath = f.split("::", 1)
            else:
                fpath = f
            required_files.append({
                "path": fpath,
                "repo": repo_path,
                "confidence": 0.80,
                "source": "curator",
            })
        elif isinstance(f, dict):
            required_files.append({
                "path": f.get("path", ""),
                "repo": f.get("repo", repo_path),
                "confidence": f.get("confidence", 0.80),
                "source": "curator",
            })
    return required_files


def migrate_task(
    csb_task_dir: Path,
    output_base: Path,
    canonical_index: dict[str, dict[str, Any]],
    *,
    validate: bool = False,
) -> MigrationResult:
    """Migrate a single CSB task to EnterpriseBench format."""
    warnings: list[MigrationWarning] = []
    errors: list[str] = []
    metadata_sources: list[str] = []

    task_dir_name = csb_task_dir.name

    # --- Read CSB sources ---

    # 1. task.toml
    csb_task = _read_toml(csb_task_dir / "task.toml")
    if csb_task is None:
        return MigrationResult(
            task_id=task_dir_name,
            success=False,
            errors=["task.toml not found"],
        )
    metadata_sources.append("task.toml")

    # Extract task ID from CSB task.toml
    raw_id = (
        csb_task.get("task", {}).get("id")
        or csb_task.get("task", {}).get("name")
        or csb_task.get("metadata", {}).get("name")
        or task_dir_name
    )

    # 2. CANONICAL.json entry
    canonical_entry = canonical_index.get(raw_id.lower()) or canonical_index.get(task_dir_name.lower())
    if canonical_entry:
        metadata_sources.append("CANONICAL.json")
    else:
        warnings.append(MigrationWarning(
            field="canonical",
            message=f"No CANONICAL.json entry found for '{raw_id}'",
        ))

    # 3. ground_truth_meta.json
    gt_meta = _read_json(csb_task_dir / "tests" / "ground_truth_meta.json")
    if gt_meta:
        metadata_sources.append("ground_truth_meta.json")

    # 4. task_spec.json
    task_spec = _read_json(csb_task_dir / "tests" / "task_spec.json")
    if task_spec:
        metadata_sources.append("task_spec.json")

    # 5. instruction.md
    instruction = _read_text(csb_task_dir / "instruction.md")
    if instruction:
        metadata_sources.append("instruction.md")
    else:
        warnings.append(MigrationWarning(
            field="task.prompt",
            message="instruction.md not found, using description as prompt",
        ))

    # 6. ground_truth.json
    gt_json = _read_json(csb_task_dir / "tests" / "ground_truth.json")
    if gt_json:
        metadata_sources.append("ground_truth.json")

    # --- Map fields ---

    eb_id = _normalize_id(raw_id)
    csb_task_section = csb_task.get("task", {})
    csb_meta = csb_task.get("metadata", {})

    # Suite
    eb_suite = _determine_suite(csb_task_dir, canonical_entry, warnings)

    # Difficulty
    raw_difficulty = csb_task_section.get("difficulty", "hard")
    eb_difficulty = DIFFICULTY_MAP.get(raw_difficulty, "hard")

    # Duration
    time_limit_sec = csb_task_section.get("time_limit_sec", 900)
    duration_minutes = max(5, min(480, time_limit_sec // 60))

    # Prompt
    prompt = instruction or csb_meta.get("description", "") or csb_task.get("verification", {}).get("description", "")
    if not prompt:
        prompt = f"Complete task {raw_id}"
        warnings.append(MigrationWarning(field="task.prompt", message="No prompt content found"))

    # Description
    description = (
        csb_meta.get("description", "")
        or csb_task.get("verification", {}).get("description", "")
        or (canonical_entry or {}).get("metadata", {}).get("description", "")
        or f"Migrated from CSB: {raw_id}"
    )

    # Repos
    repo_str = csb_task_section.get("repo", "")
    if not repo_str and canonical_entry:
        repo_str = canonical_entry.get("task", {}).get("repo", "")
    repo_info = _parse_repo_field(repo_str)
    repos = [repo_info] if repo_str else []
    if not repos:
        warnings.append(MigrationWarning(field="repos", message="No repo field found in CSB task"))
        # Create a placeholder
        repos = [{"url": "github.com/unknown/repo", "rev": "HEAD", "path": "repo", "role": "primary"}]

    # Artifacts
    required_artifacts = _determine_artifacts(csb_task, canonical_entry)

    # Ground truth
    gt_tiers = _determine_gt_tiers(gt_meta)
    gt_required_files = _build_ground_truth_files(gt_json, task_spec, repos[0]["path"])

    # Stratum
    stratum = _determine_stratum(len(repos), csb_task, canonical_entry)

    # Language
    language = csb_task_section.get("language") or csb_task.get("metadata", {}).get("language", "")
    if not language and canonical_entry:
        language = canonical_entry.get("task", {}).get("language", "")
    languages = [language] if language else []

    # Tool access
    org_scale = csb_task_section.get("org_scale", False)
    if canonical_entry:
        org_scale = org_scale or canonical_entry.get("task", {}).get("org_scale", False)
    mcp_benefit = "high" if org_scale else "medium"

    # CSB lineage
    origin_suite = csb_task_dir.parent.name
    if canonical_entry:
        origin_suite = canonical_entry.get("metadata", {}).get("origin_suite") or origin_suite

    # Sourcegraph mirror info
    sg_mirrors: list[dict[str, str]] = []
    if repo_str and repo_str.startswith("sg-evals/"):
        sg_mirrors.append({"repo": repos[0]["url"], "mirror_id": repo_str})

    # LOC from task_spec
    total_loc = None
    if task_spec:
        total_loc = task_spec.get("total_loc")

    # --- Build EB TOML ---
    eb_data = _build_toml_string(
        eb_id=eb_id,
        eb_suite=eb_suite,
        eb_difficulty=eb_difficulty,
        duration_minutes=duration_minutes,
        description=description,
        prompt=prompt,
        repos=repos,
        languages=languages,
        total_loc=total_loc,
        required_artifacts=required_artifacts,
        gt_tiers=gt_tiers,
        gt_required_files=gt_required_files,
        stratum=stratum,
        mcp_benefit=mcp_benefit,
        sg_mirrors=sg_mirrors,
        csb_id=raw_id,
        origin_suite=origin_suite,
        metadata_sources=metadata_sources,
    )

    # --- Write output ---
    output_dir = output_base / eb_suite / task_dir_name
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "task.toml"
    output_path.write_text(eb_data, encoding="utf-8")

    # Copy instruction files
    for fname in ("instruction.md", "instruction_mcp.md"):
        src = csb_task_dir / fname
        if src.exists():
            shutil.copy2(src, output_dir / fname)

    # --- Validate if requested ---
    validation_errors: list[str] = []
    if validate:
        validation_errors = _validate_output(output_path)

    return MigrationResult(
        task_id=eb_id,
        success=len(errors) == 0,
        output_path=str(output_path),
        warnings=warnings,
        errors=errors,
        validation_errors=validation_errors,
    )


def _build_toml_string(
    *,
    eb_id: str,
    eb_suite: str,
    eb_difficulty: str,
    duration_minutes: int,
    description: str,
    prompt: str,
    repos: list[dict[str, Any]],
    languages: list[str],
    total_loc: int | None,
    required_artifacts: list[str],
    gt_tiers: list[str],
    gt_required_files: list[dict[str, Any]],
    stratum: str,
    mcp_benefit: str,
    sg_mirrors: list[dict[str, str]],
    csb_id: str,
    origin_suite: str,
    metadata_sources: list[str],
) -> str:
    """Build a TOML string for the EB task (manual serialization for control)."""
    lines: list[str] = []

    lines.append(f'# Migrated from CodeScaleBench: {csb_id}')
    lines.append(f'# Origin suite: {origin_suite}')
    lines.append("")

    # Top-level
    lines.append(f'difficulty_stratum = "{stratum}"')
    lines.append("")

    # [task]
    lines.append("[task]")
    lines.append(f'id = "{eb_id}"')
    lines.append(f'suite = "{eb_suite}"')
    lines.append(f'difficulty = "{eb_difficulty}"')
    lines.append(f"estimated_duration_minutes = {duration_minutes}")
    lines.append('session_type = "single"')
    lines.append(f'description = "{_escape_toml(description)}"')
    lines.append(f'prompt = """\n{prompt}"""')
    lines.append("")

    # [[repos]]
    for repo in repos:
        lines.append("[[repos]]")
        lines.append(f'url = "{repo["url"]}"')
        lines.append(f'rev = "{repo["rev"]}"')
        lines.append(f'path = "{repo["path"]}"')
        lines.append(f'role = "{repo.get("role", "primary")}"')
        lines.append("")

    # [metadata]
    lines.append("[metadata]")
    if languages:
        lang_str = ", ".join(f'"{l}"' for l in languages)
        lines.append(f"languages = [{lang_str}]")
    if total_loc is not None:
        lines.append(f"total_loc = {total_loc}")
    lines.append("dependency_depth = 1")
    lines.append("")

    # [[checkpoints]] - single checkpoint from CSB test.sh
    lines.append("[[checkpoints]]")
    lines.append('name = "primary_verification"')
    lines.append("weight = 1.0")
    lines.append('verifier = "tests/test.sh"')
    lines.append(f'description = "Primary verification: {_escape_toml(description)}"')
    lines.append("timeout_seconds = 120")
    lines.append("")

    # [artifacts]
    lines.append("[artifacts]")
    art_str = ", ".join(f'"{a}"' for a in required_artifacts)
    lines.append(f"required = [{art_str}]")
    lines.append("")

    # [tool_access]
    lines.append("[tool_access]")
    lines.append(f'expected_mcp_benefit = "{mcp_benefit}"')
    for mirror in sg_mirrors:
        lines.append("")
        lines.append("[[tool_access.sourcegraph_mirrors]]")
        lines.append(f'repo = "{mirror["repo"]}"')
        lines.append(f'mirror_id = "{mirror["mirror_id"]}"')
    lines.append("")

    # [ground_truth]
    lines.append("[ground_truth]")
    tiers_str = ", ".join(f'"{t}"' for t in gt_tiers)
    lines.append(f"tiers = [{tiers_str}]")
    for gf in gt_required_files[:5]:
        lines.append("")
        lines.append("[[ground_truth.required_files]]")
        lines.append(f'path = "{gf["path"]}"')
        lines.append(f'repo = "{gf["repo"]}"')
        if gf.get("confidence"):
            lines.append(f'confidence = {gf["confidence"]}')
        if gf.get("source"):
            lines.append(f'source = "{gf["source"]}"')
    lines.append("")

    # [csb_lineage]
    lines.append("[csb_lineage]")
    lines.append(f'parent_csb_id = "{csb_id}"')
    lines.append(f'origin_suite = "{origin_suite}"')
    lines.append('migration_status = "metadata_merged"')
    sources_str = ", ".join(f'"{s}"' for s in metadata_sources)
    lines.append(f"metadata_sources = [{sources_str}]")
    lines.append("")

    return "\n".join(lines) + "\n"


def _escape_toml(s: str) -> str:
    """Escape a string for use in TOML double-quoted strings."""
    return (
        s.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", " ")
        .replace("\r", "")
        .replace("\t", " ")
    )


def _validate_output(output_path: Path) -> list[str]:
    """Run eb_verify validation on the output file."""
    validation_errors: list[str] = []
    try:
        # Add lib to path for importing
        lib_path = Path(__file__).parent.parent / "lib"
        if str(lib_path) not in sys.path:
            sys.path.insert(0, str(lib_path))
        from eb_verify.schema_validator import validate_task

        result = validate_task(str(output_path))
        if not result.valid:
            for err in result.errors:
                validation_errors.append(f"{err.field}: {err.message}")
        for warn in result.warnings:
            validation_errors.append(f"[WARN] {warn.field}: {warn.message}")
    except Exception as exc:
        validation_errors.append(f"Validation error: {exc}")
    return validation_errors


def run_batch(
    suite_dir: Path,
    output_base: Path,
    canonical_index: dict[str, dict[str, Any]],
    *,
    limit: int | None = None,
    validate: bool = False,
) -> list[MigrationResult]:
    """Migrate all tasks in a CSB suite directory."""
    results: list[MigrationResult] = []
    task_dirs = sorted(d for d in suite_dir.iterdir() if d.is_dir())
    if limit:
        task_dirs = task_dirs[:limit]

    for task_dir in task_dirs:
        if not (task_dir / "task.toml").exists():
            continue
        result = migrate_task(task_dir, output_base, canonical_index, validate=validate)
        results.append(result)
        status = "OK" if result.success else "FAIL"
        val_status = ""
        if validate:
            val_status = f" [validation: {len(result.validation_errors)} errors]"
        print(f"  {status}: {result.task_id}{val_status}")

    return results


def generate_report(
    results: list[MigrationResult],
    output_path: Path,
) -> None:
    """Generate a migration pilot report."""
    total = len(results)
    succeeded = sum(1 for r in results if r.success)
    failed = total - succeeded
    val_pass = sum(1 for r in results if r.success and not r.validation_errors)
    val_fail = sum(1 for r in results if r.success and r.validation_errors)

    lines: list[str] = []
    lines.append("# CSB → EnterpriseBench Migration Pilot Report")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Tasks attempted**: {total}")
    lines.append(f"- **Migration succeeded**: {succeeded}")
    lines.append(f"- **Migration failed**: {failed}")
    lines.append(f"- **Validation passed**: {val_pass}")
    lines.append(f"- **Validation failed**: {val_fail}")
    lines.append("")

    lines.append("## Per-Task Results")
    lines.append("")
    lines.append("| Task ID | Migration | Validation | Warnings | Errors |")
    lines.append("|---------|-----------|------------|----------|--------|")
    for r in results:
        mig_status = "Pass" if r.success else "Fail"
        val_status = "Pass" if (r.success and not r.validation_errors) else f"{len(r.validation_errors)} errors"
        warn_count = len(r.warnings)
        err_summary = "; ".join(r.errors[:2]) if r.errors else "-"
        lines.append(f"| {r.task_id} | {mig_status} | {val_status} | {warn_count} | {err_summary} |")
    lines.append("")

    # Common validation errors
    all_val_errors: list[str] = []
    for r in results:
        all_val_errors.extend(r.validation_errors)

    if all_val_errors:
        lines.append("## Common Validation Errors")
        lines.append("")
        # Group by field
        error_counts: dict[str, int] = {}
        for err in all_val_errors:
            field = err.split(":")[0] if ":" in err else err
            error_counts[field] = error_counts.get(field, 0) + 1
        for field, count in sorted(error_counts.items(), key=lambda x: -x[1]):
            lines.append(f"- **{field}**: {count} occurrence(s)")
        lines.append("")

    # Warnings
    all_warnings: list[str] = []
    for r in results:
        for w in r.warnings:
            all_warnings.append(f"{w.field}: {w.message}")

    if all_warnings:
        lines.append("## Common Warnings")
        lines.append("")
        warning_counts: dict[str, int] = {}
        for w in all_warnings:
            field = w.split(":")[0]
            warning_counts[field] = warning_counts.get(field, 0) + 1
        for field, count in sorted(warning_counts.items(), key=lambda x: -x[1]):
            lines.append(f"- **{field}**: {count} occurrence(s)")
        lines.append("")

    # Unmapped fields
    lines.append("## Fields That Could Not Be Auto-Mapped")
    lines.append("")
    lines.append("- `metadata.max_complexity` — not available in CSB metadata")
    lines.append("- `metadata.frameworks` — available in reviewers.json but not reliably structured")
    lines.append("- `metadata.multi_repo_pattern` — requires manual classification")
    lines.append("- `ground_truth.sufficient_files` — CSB only has required files in ground_truth.json")
    lines.append("- `tool_access.mcp_benefit_rationale` — requires human judgment")
    lines.append("- Multiple checkpoints — CSB has single test.sh; splitting requires manual analysis")
    lines.append("")

    # Validation error details
    if all_val_errors:
        lines.append("## Validation Error Details")
        lines.append("")
        for r in results:
            if r.validation_errors:
                lines.append(f"### {r.task_id}")
                lines.append("")
                for err in r.validation_errors:
                    lines.append(f"- {err}")
                lines.append("")

    lines.append("## Recommendations for Full Migration")
    lines.append("")
    lines.append("1. **ID normalization**: Several CSB IDs use mixed case (e.g., 'CCX-compliance-052').")
    lines.append("   The normalizer handles this, but manual review recommended for edge cases.")
    lines.append("2. **Multi-checkpoint splitting**: All migrated tasks have a single checkpoint (weight=1.0).")
    lines.append("   For the full migration, analyze test.sh to identify natural checkpoints.")
    lines.append("3. **Ground truth enrichment**: CSB ground_truth.json files are curator-generated.")
    lines.append("   Add deterministic tier via static analysis before benchmark runs.")
    lines.append("4. **Repo URL resolution**: sg-evals mirror URLs need mapping to real GitHub repos.")
    lines.append("   Build a mirror→canonical URL lookup table.")
    lines.append("5. **SDLC tasks without repo field**: Some SDLC tasks don't specify a repo in task.toml.")
    lines.append("   These need manual repo assignment from the task's Docker environment.")
    lines.append("6. **Stratum classification**: Auto-classification uses repo count + org_scale.")
    lines.append("   Manual review needed for calibration vs large_single boundary.")
    lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nReport written to: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate CodeScaleBench tasks to EnterpriseBench format",
    )
    parser.add_argument(
        "csb_task_dir",
        nargs="?",
        help="Path to a single CSB task directory",
    )
    parser.add_argument(
        "--batch",
        help="Path to a CSB suite directory (migrate all tasks)",
    )
    parser.add_argument(
        "--output",
        default=str(Path(__file__).parent.parent / "benchmarks"),
        help="Output base directory (default: benchmarks/)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of tasks in batch mode",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run eb_verify validation on output",
    )
    parser.add_argument(
        "--report",
        help="Path to write migration report (default: docs/migration_pilot_report.md)",
    )
    parser.add_argument(
        "--pilot",
        action="store_true",
        help="Run pilot migration on 10 representative tasks",
    )

    args = parser.parse_args()

    if not args.csb_task_dir and not args.batch and not args.pilot:
        parser.error("Provide a CSB task directory, --batch suite directory, or --pilot")

    output_base = Path(args.output)
    print("Loading CANONICAL.json index...")
    canonical_index = _load_canonical()
    print(f"  Indexed {len(canonical_index)} tasks")

    results: list[MigrationResult] = []

    if args.pilot:
        # Pilot: 10 representative tasks from different suites
        csb_benchmarks = CSB_ROOT / "benchmarks"
        pilot_suites = [
            "csb_org_compliance",
            "csb_org_incident",
            "csb_org_crossrepo",
            "csb_sdlc_debug",
            "csb_sdlc_feature",
            "csb_sdlc_fix",
            "csb_sdlc_refactor",
            "csb_sdlc_secure",
            "csb_sdlc_test",
            "csb_sdlc_design",
        ]
        for suite in pilot_suites:
            suite_dir = csb_benchmarks / suite
            if not suite_dir.exists():
                print(f"  SKIP: {suite} (directory not found)")
                continue
            task_dirs = sorted(d for d in suite_dir.iterdir() if d.is_dir())
            if not task_dirs:
                print(f"  SKIP: {suite} (no task directories)")
                continue
            task_dir = task_dirs[0]
            print(f"\nMigrating {suite}/{task_dir.name}...")
            result = migrate_task(task_dir, output_base, canonical_index, validate=True)
            results.append(result)
            status = "OK" if result.success else "FAIL"
            val_count = len(result.validation_errors)
            print(f"  {status}: {result.task_id} [validation: {val_count} errors, {len(result.warnings)} warnings]")
            if result.validation_errors:
                for err in result.validation_errors[:3]:
                    print(f"    - {err}")

        report_path = Path(args.report or str(Path(__file__).parent.parent / "docs" / "migration_pilot_report.md"))
        generate_report(results, report_path)

    elif args.batch:
        suite_dir = Path(args.batch)
        print(f"\nBatch migrating from: {suite_dir}")
        results = run_batch(
            suite_dir, output_base, canonical_index,
            limit=args.limit, validate=args.validate,
        )
    else:
        task_dir = Path(args.csb_task_dir)
        print(f"\nMigrating: {task_dir}")
        result = migrate_task(task_dir, output_base, canonical_index, validate=args.validate)
        results = [result]
        status = "OK" if result.success else "FAIL"
        print(f"  {status}: {result.task_id}")
        if result.warnings:
            for w in result.warnings:
                print(f"  WARN: {w.field}: {w.message}")
        if result.validation_errors:
            for err in result.validation_errors:
                print(f"  VALIDATION: {err}")

    # Summary
    total = len(results)
    ok = sum(1 for r in results if r.success)
    print(f"\n{'='*50}")
    print(f"Total: {total}, Succeeded: {ok}, Failed: {total - ok}")
    if any(r.validation_errors for r in results):
        val_ok = sum(1 for r in results if r.success and not r.validation_errors)
        print(f"Validation: {val_ok}/{ok} passed")


if __name__ == "__main__":
    main()
