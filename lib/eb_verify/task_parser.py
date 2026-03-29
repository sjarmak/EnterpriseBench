"""
Parse task.toml files into structured TaskDefinition objects.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]


@dataclass(frozen=True)
class RepoSpec:
    url: str
    rev: str
    path: str
    role: str = "primary"


@dataclass(frozen=True)
class Checkpoint:
    name: str
    weight: float
    verifier: str  # relative path to verifier script
    description: str = ""
    timeout_seconds: int = 120


@dataclass(frozen=True)
class ArtifactSpec:
    required: List[str] = field(default_factory=list)
    optional: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class GroundTruthFile:
    path: str
    repo: str
    line_range: Optional[str] = None
    confidence: Optional[float] = None
    source: Optional[str] = None


@dataclass(frozen=True)
class GroundTruth:
    tiers: List[str] = field(default_factory=list)
    required_files: List[GroundTruthFile] = field(default_factory=list)
    sufficient_files: List[GroundTruthFile] = field(default_factory=list)


@dataclass(frozen=True)
class SourcegraphMirror:
    repo: str
    mirror_id: str


@dataclass(frozen=True)
class ToolAccess:
    expected_mcp_benefit: Optional[str] = None
    mcp_benefit_rationale: Optional[str] = None
    sourcegraph_mirrors: List[SourcegraphMirror] = field(default_factory=list)


@dataclass(frozen=True)
class CSBLineage:
    parent_csb_id: Optional[str] = None
    origin_suite: Optional[str] = None
    migration_status: Optional[str] = None
    bugs_fixed: List[str] = field(default_factory=list)
    metadata_sources: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class EventConfig:
    event_stream_path: Optional[str] = None  # maps from events.event_file in TOML
    oracle_actions_path: Optional[str] = None  # maps from events.oracle_actions in TOML
    session_count: Optional[int] = None  # maps from task.session_count in TOML


@dataclass(frozen=True)
class ResumeState:
    branch: Optional[str] = None
    progress_doc: Optional[str] = None


@dataclass(frozen=True)
class TaskMetadata:
    languages: List[str] = field(default_factory=list)
    total_loc: Optional[int] = None
    max_complexity: Optional[float] = None
    dependency_depth: Optional[int] = None
    frameworks: List[str] = field(default_factory=list)
    multi_repo_pattern: Optional[str] = None


@dataclass(frozen=True)
class TaskDefinition:
    id: str
    suite: str
    difficulty: str
    session_type: str
    description: str = ""
    prompt: str = ""
    estimated_duration_minutes: int = 30
    repos: List[RepoSpec] = field(default_factory=list)
    checkpoints: List[Checkpoint] = field(default_factory=list)
    artifacts: ArtifactSpec = field(default_factory=ArtifactSpec)
    difficulty_stratum: Optional[str] = None
    ground_truth: Optional[GroundTruth] = None
    tool_access: Optional[ToolAccess] = None
    csb_lineage: Optional[CSBLineage] = None
    event_config: Optional[EventConfig] = None
    resume_state: Optional[ResumeState] = None
    metadata: Optional[TaskMetadata] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def workspace_root(self) -> Path:
        return Path("/workspace")


# --- Helper parsers ---

def _parse_ground_truth_file(f: Dict[str, Any]) -> GroundTruthFile:
    return GroundTruthFile(
        path=f["path"],
        repo=f["repo"],
        line_range=f.get("line_range"),
        confidence=f.get("confidence"),
        source=f.get("source"),
    )


def _parse_ground_truth(raw_gt: Dict[str, Any]) -> GroundTruth:
    return GroundTruth(
        tiers=raw_gt.get("tiers", []),
        required_files=[_parse_ground_truth_file(f) for f in raw_gt.get("required_files", [])],
        sufficient_files=[_parse_ground_truth_file(f) for f in raw_gt.get("sufficient_files", [])],
    )


def _parse_tool_access(raw_ta: Dict[str, Any]) -> ToolAccess:
    mirrors = [
        SourcegraphMirror(repo=m["repo"], mirror_id=m["mirror_id"])
        for m in raw_ta.get("sourcegraph_mirrors", [])
    ]
    return ToolAccess(
        expected_mcp_benefit=raw_ta.get("expected_mcp_benefit"),
        mcp_benefit_rationale=raw_ta.get("mcp_benefit_rationale"),
        sourcegraph_mirrors=mirrors,
    )


def _parse_csb_lineage(raw_lin: Dict[str, Any]) -> CSBLineage:
    return CSBLineage(
        parent_csb_id=raw_lin.get("parent_csb_id"),
        origin_suite=raw_lin.get("origin_suite"),
        migration_status=raw_lin.get("migration_status"),
        bugs_fixed=raw_lin.get("bugs_fixed", []),
        metadata_sources=raw_lin.get("metadata_sources", []),
    )


def _parse_event_config(raw_events: Dict[str, Any], task_section: Dict[str, Any]) -> EventConfig:
    return EventConfig(
        event_stream_path=raw_events.get("event_file"),
        oracle_actions_path=raw_events.get("oracle_actions"),
        session_count=task_section.get("session_count"),
    )


def _parse_resume_state(raw_rs: Dict[str, Any]) -> ResumeState:
    return ResumeState(
        branch=raw_rs.get("branch"),
        progress_doc=raw_rs.get("progress_doc"),
    )


def _parse_metadata(raw_meta: Dict[str, Any]) -> TaskMetadata:
    return TaskMetadata(
        languages=raw_meta.get("languages", []),
        total_loc=raw_meta.get("total_loc"),
        max_complexity=raw_meta.get("max_complexity"),
        dependency_depth=raw_meta.get("dependency_depth"),
        frameworks=raw_meta.get("frameworks", []),
        multi_repo_pattern=raw_meta.get("multi_repo_pattern"),
    )


def parse_task(path: str | Path) -> TaskDefinition:
    """Parse a task.toml file and return a TaskDefinition."""
    path = Path(path)
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    task_section = raw.get("task", {})
    repos = [
        RepoSpec(
            url=r["url"],
            rev=r["rev"],
            path=r["path"],
            role=r.get("role", "primary"),
        )
        for r in raw.get("repos", [])
    ]
    checkpoints = [
        Checkpoint(
            name=c["name"],
            weight=c["weight"],
            verifier=c["verifier"],
            description=c.get("description", ""),
            timeout_seconds=c.get("timeout_seconds", 120),
        )
        for c in raw.get("checkpoints", [])
    ]
    artifacts_raw = raw.get("artifacts", {})
    artifacts = ArtifactSpec(
        required=artifacts_raw.get("required", []),
        optional=artifacts_raw.get("optional", []),
    )

    raw_gt = raw.get("ground_truth")
    ground_truth = _parse_ground_truth(raw_gt) if raw_gt is not None else None

    raw_ta = raw.get("tool_access")
    tool_access = _parse_tool_access(raw_ta) if raw_ta is not None else None

    raw_lin = raw.get("csb_lineage")
    csb_lineage = _parse_csb_lineage(raw_lin) if raw_lin is not None else None

    raw_events = raw.get("events")
    event_config = (
        _parse_event_config(raw_events, task_section) if raw_events is not None else None
    )

    raw_rs = raw.get("resume_state")
    resume_state = _parse_resume_state(raw_rs) if raw_rs is not None else None

    raw_meta = raw.get("metadata")
    metadata = _parse_metadata(raw_meta) if raw_meta is not None else None

    try:
      _id = task_section["id"]
      _suite = task_section["suite"]
      _difficulty = task_section["difficulty"]
      _session_type = task_section["session_type"]
    except KeyError as e:
        raise ValueError(f"task.toml missing required field: {e}") from e

    return TaskDefinition(
        id=_id,
        suite=_suite,
        difficulty=_difficulty,
        session_type=_session_type,
        description=task_section.get("description", ""),
        prompt=task_section.get("prompt", ""),
        estimated_duration_minutes=task_section.get("estimated_duration_minutes", 30),
        repos=repos,
        checkpoints=checkpoints,
        artifacts=artifacts,
        difficulty_stratum=raw.get("difficulty_stratum"),
        ground_truth=ground_truth,
        tool_access=tool_access,
        csb_lineage=csb_lineage,
        event_config=event_config,
        resume_state=resume_state,
        metadata=metadata,
        raw=raw,
    )
