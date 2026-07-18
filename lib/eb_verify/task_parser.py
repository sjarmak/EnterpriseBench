"""
Parse task.toml files into structured TaskDefinition objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    require_grounded_citations: bool = False


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
    verification_modes: List[str] = field(default_factory=lambda: ["deterministic"])
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


def _require(entry: Dict[str, Any], key: str, *, path: Path, section: str) -> Any:
    """Look up a required key, raising ValueError (not bare KeyError) if absent.

    Every malformed-task.toml failure should reach a caller as a single
    exception type naming the file and the missing key, so one honest
    ``except (OSError, ValueError)`` clause covers the whole contract.
    """
    try:
        return entry[key]
    except KeyError:
        raise ValueError(
            f"{path}: {section} entry missing required field '{key}'"
        ) from None


def _parse_ground_truth_file(f: Dict[str, Any], *, path: Path) -> GroundTruthFile:
    return GroundTruthFile(
        path=_require(f, "path", path=path, section="ground_truth file"),
        repo=_require(f, "repo", path=path, section="ground_truth file"),
        line_range=f.get("line_range"),
        confidence=f.get("confidence"),
        source=f.get("source"),
    )


def _parse_ground_truth(raw_gt: Dict[str, Any], *, path: Path) -> GroundTruth:
    return GroundTruth(
        tiers=raw_gt.get("tiers", []),
        required_files=[
            _parse_ground_truth_file(f, path=path)
            for f in raw_gt.get("required_files", [])
        ],
        sufficient_files=[
            _parse_ground_truth_file(f, path=path)
            for f in raw_gt.get("sufficient_files", [])
        ],
        require_grounded_citations=bool(
            raw_gt.get("require_grounded_citations", False)
        ),
    )


def _parse_tool_access(raw_ta: Dict[str, Any], *, path: Path) -> ToolAccess:
    mirrors = [
        SourcegraphMirror(
            repo=_require(m, "repo", path=path, section="tool_access mirror"),
            mirror_id=_require(m, "mirror_id", path=path, section="tool_access mirror"),
        )
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


def _parse_event_config(
    raw_events: Dict[str, Any], task_section: Dict[str, Any]
) -> EventConfig:
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
    """Parse a task.toml file and return a TaskDefinition.

    Failure contract: a malformed task.toml surfaces as exactly two exception
    types. ``OSError`` if the file can't be read; ``ValueError`` for any bad
    *content* — TOML syntax errors (``tomllib.TOMLDecodeError`` is a
    ``ValueError``), a missing required field (via ``_require``), or a
    structurally wrong shape (a scalar where a table/array is expected, which
    the raw parsers would otherwise raise as ``KeyError``/``TypeError``/
    ``AttributeError``). Callers can therefore write one honest
    ``except (OSError, ValueError)`` rather than enumerating shape-dependent
    classes (EnterpriseBench-20nhr).
    """
    path = Path(path)
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    try:
        return _task_from_raw(raw, path=path)
    except ValueError:
        # Precise messages from _require (and any TOML-layer ValueError) pass
        # through unchanged — re-wrapping would only bury the named field.
        raise
    except (KeyError, TypeError, AttributeError) as e:
        raise ValueError(f"{path}: malformed task.toml: {e!r}") from e


def _task_from_raw(raw: Dict[str, Any], *, path: Path) -> TaskDefinition:
    task_section = raw.get("task", {})
    repos = [
        RepoSpec(
            url=_require(r, "url", path=path, section="[[repos]]"),
            rev=_require(r, "rev", path=path, section="[[repos]]"),
            path=_require(r, "path", path=path, section="[[repos]]"),
            role=r.get("role", "primary"),
        )
        for r in raw.get("repos", [])
    ]
    checkpoints = [
        Checkpoint(
            name=_require(c, "name", path=path, section="[[checkpoints]]"),
            weight=_require(c, "weight", path=path, section="[[checkpoints]]"),
            verifier=_require(c, "verifier", path=path, section="[[checkpoints]]"),
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
    ground_truth = (
        _parse_ground_truth(raw_gt, path=path) if raw_gt is not None else None
    )

    raw_ta = raw.get("tool_access")
    tool_access = _parse_tool_access(raw_ta, path=path) if raw_ta is not None else None

    raw_lin = raw.get("csb_lineage")
    csb_lineage = _parse_csb_lineage(raw_lin) if raw_lin is not None else None

    raw_events = raw.get("events")
    event_config = (
        _parse_event_config(raw_events, task_section)
        if raw_events is not None
        else None
    )

    raw_rs = raw.get("resume_state")
    resume_state = _parse_resume_state(raw_rs) if raw_rs is not None else None

    raw_meta = raw.get("metadata")
    metadata = _parse_metadata(raw_meta) if raw_meta is not None else None

    _id = _require(task_section, "id", path=path, section="[task]")
    _suite = _require(task_section, "suite", path=path, section="[task]")
    _difficulty = _require(task_section, "difficulty", path=path, section="[task]")
    _session_type = _require(task_section, "session_type", path=path, section="[task]")

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
        verification_modes=raw.get("verification_modes", ["deterministic"]),
        ground_truth=ground_truth,
        tool_access=tool_access,
        csb_lineage=csb_lineage,
        event_config=event_config,
        resume_state=resume_state,
        metadata=metadata,
        raw=raw,
    )
