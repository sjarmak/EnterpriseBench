"""Tests for eb_verify.task_parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from eb_verify.task_parser import (
    ArtifactSpec,
    CSBLineage,
    Checkpoint,
    EventConfig,
    GroundTruth,
    GroundTruthFile,
    RepoSpec,
    ResumeState,
    SourcegraphMirror,
    TaskDefinition,
    TaskMetadata,
    ToolAccess,
    parse_task,
)


# ---------------------------------------------------------------------------
# Parse EXAMPLE_TASK.toml — comprehensive field access
# ---------------------------------------------------------------------------

class TestExampleTask:
    def test_parse_succeeds(self, example_task_path):
        task = parse_task(example_task_path)
        assert task.id == "dep-mgmt-grpc-proto-bump-001"

    def test_suite_and_difficulty(self, example_task_path):
        task = parse_task(example_task_path)
        assert task.suite == "dependency_management"
        assert task.difficulty == "hard"

    def test_session_type(self, example_task_path):
        task = parse_task(example_task_path)
        assert task.session_type == "single"

    def test_repos(self, example_task_path):
        task = parse_task(example_task_path)
        assert len(task.repos) == 2
        grpc = next(r for r in task.repos if "grpc" in r.url)
        assert grpc.rev == "v1.60.0"
        assert grpc.role == "dependency"
        etcd = next(r for r in task.repos if "etcd" in r.url)
        assert etcd.path == "etcd"
        assert etcd.role == "primary"

    def test_checkpoints(self, example_task_path):
        task = parse_task(example_task_path)
        assert len(task.checkpoints) == 3
        weights = [cp.weight for cp in task.checkpoints]
        assert abs(sum(weights) - 1.0) < 0.01
        assert task.checkpoints[0].name == "identify_affected_files"
        assert task.checkpoints[0].timeout_seconds == 60

    def test_artifacts(self, example_task_path):
        task = parse_task(example_task_path)
        assert "code_patch" in task.artifacts.required
        assert "migration_guide" in task.artifacts.optional

    def test_difficulty_stratum(self, example_task_path):
        task = parse_task(example_task_path)
        assert task.difficulty_stratum == "dual_repo"

    def test_ground_truth(self, example_task_path):
        task = parse_task(example_task_path)
        assert task.ground_truth is not None
        assert "deterministic" in task.ground_truth.tiers
        assert len(task.ground_truth.required_files) == 3
        first = task.ground_truth.required_files[0]
        assert first.path == "clientv3/client.go"
        assert first.repo == "etcd"
        assert first.line_range == "45-120"
        assert first.confidence == 0.95

    def test_tool_access(self, example_task_path):
        task = parse_task(example_task_path)
        assert task.tool_access is not None
        assert task.tool_access.expected_mcp_benefit == "high"
        assert len(task.tool_access.sourcegraph_mirrors) == 2
        mirror = task.tool_access.sourcegraph_mirrors[0]
        assert isinstance(mirror, SourcegraphMirror)
        assert mirror.mirror_id == "sg-mirror-grpc-go-v1.60.0"

    def test_csb_lineage(self, example_task_path):
        task = parse_task(example_task_path)
        assert task.csb_lineage is not None
        assert task.csb_lineage.parent_csb_id == "csb_org_dependency_grpc_proto_bump_042"
        assert task.csb_lineage.migration_status == "verified"
        assert "csb-bug-007" in task.csb_lineage.bugs_fixed

    def test_metadata(self, example_task_path):
        task = parse_task(example_task_path)
        assert task.metadata is not None
        assert "go" in task.metadata.languages
        assert task.metadata.total_loc == 1_400_000
        assert task.metadata.multi_repo_pattern == "propagate"

    def test_workspace_root(self, example_task_path):
        task = parse_task(example_task_path)
        assert task.workspace_root == Path("/workspace")

    def test_raw_dict_preserved(self, example_task_path):
        task = parse_task(example_task_path)
        assert "task" in task.raw
        assert task.raw["task"]["id"] == "dep-mgmt-grpc-proto-bump-001"


# ---------------------------------------------------------------------------
# Parse minimal valid task
# ---------------------------------------------------------------------------

class TestValidTask:
    def test_parse_minimal(self, valid_task_path):
        task = parse_task(valid_task_path)
        assert task.id == "test-task-001"
        assert task.suite == "dependency_management"

    def test_optional_fields_absent(self, valid_task_path):
        task = parse_task(valid_task_path)
        # These optional sections are not in valid_task.toml
        assert task.ground_truth is None
        assert task.tool_access is None
        assert task.csb_lineage is None
        assert task.event_config is None
        assert task.resume_state is None
        assert task.metadata is None
        assert task.difficulty_stratum is None

    def test_checkpoints_parsed(self, valid_task_path):
        task = parse_task(valid_task_path)
        assert len(task.checkpoints) == 2
        assert task.checkpoints[0].name == "step_one"
        assert task.checkpoints[1].name == "step_two"

    def test_default_timeout(self, valid_task_path):
        task = parse_task(valid_task_path)
        # timeout_seconds defaults to 120 when not specified
        assert task.checkpoints[0].timeout_seconds == 120

    def test_default_estimated_duration(self, valid_task_path):
        task = parse_task(valid_task_path)
        assert task.estimated_duration_minutes == 30


# ---------------------------------------------------------------------------
# Chain session task
# ---------------------------------------------------------------------------

class TestChainTask:
    def test_session_type_chain(self, chain_task_path):
        task = parse_task(chain_task_path)
        assert task.session_type == "chain"

    def test_event_config_none_for_chain(self, chain_task_path):
        # chain tasks don't have an events section
        task = parse_task(chain_task_path)
        assert task.event_config is None


# ---------------------------------------------------------------------------
# Frozen dataclass immutability
# ---------------------------------------------------------------------------

class TestImmutability:
    def test_task_definition_frozen(self, valid_task_path):
        task = parse_task(valid_task_path)
        with pytest.raises((AttributeError, TypeError)):
            task.id = "mutated"  # type: ignore[misc]

    def test_checkpoint_frozen(self, valid_task_path):
        task = parse_task(valid_task_path)
        cp = task.checkpoints[0]
        with pytest.raises((AttributeError, TypeError)):
            cp.weight = 0.99  # type: ignore[misc]

    def test_repo_spec_frozen(self, valid_task_path):
        task = parse_task(valid_task_path)
        repo = task.repos[0]
        with pytest.raises((AttributeError, TypeError)):
            repo.path = "hacked"  # type: ignore[misc]

    def test_artifact_spec_frozen(self, valid_task_path):
        task = parse_task(valid_task_path)
        with pytest.raises((AttributeError, TypeError)):
            task.artifacts.required = []  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestParseErrors:
    def test_nonexistent_file(self, tmp_path):
        with pytest.raises((FileNotFoundError, OSError)):
            parse_task(tmp_path / "nonexistent.toml")

    def test_invalid_toml_syntax(self, tmp_path):
        bad = tmp_path / "bad.toml"
        bad.write_bytes(b"[task\nid = not_valid toml ][[[")
        with pytest.raises(Exception):
            parse_task(bad)

    def test_missing_required_field(self, tmp_path):
        # Missing task.suite
        minimal = tmp_path / "missing_field.toml"
        minimal.write_bytes(b"""
[task]
id = "x"
difficulty = "medium"
session_type = "single"
""")
        with pytest.raises((KeyError, Exception)):
            parse_task(minimal)


# ---------------------------------------------------------------------------
# Dataclass construction helpers
# ---------------------------------------------------------------------------

class TestDataclassConstruction:
    def test_repo_spec_defaults(self):
        r = RepoSpec(url="http://x", rev="main", path="x")
        assert r.role == "primary"

    def test_checkpoint_defaults(self):
        cp = Checkpoint(name="c", weight=1.0, verifier="v.sh")
        assert cp.description == ""
        assert cp.timeout_seconds == 120

    def test_ground_truth_file_optional_fields(self):
        gtf = GroundTruthFile(path="a.py", repo="myrepo")
        assert gtf.line_range is None
        assert gtf.confidence is None
        assert gtf.source is None

    def test_ground_truth_defaults(self):
        gt = GroundTruth()
        assert gt.tiers == []
        assert gt.required_files == []
        assert gt.sufficient_files == []

    def test_tool_access_defaults(self):
        ta = ToolAccess()
        assert ta.expected_mcp_benefit is None
        assert ta.sourcegraph_mirrors == []

    def test_csb_lineage_defaults(self):
        lin = CSBLineage()
        assert lin.bugs_fixed == []
        assert lin.metadata_sources == []

    def test_task_metadata_defaults(self):
        m = TaskMetadata()
        assert m.languages == []
        assert m.frameworks == []
        assert m.total_loc is None

    def test_event_config_defaults(self):
        ec = EventConfig()
        assert ec.event_stream_path is None
        assert ec.session_count is None

    def test_resume_state_defaults(self):
        rs = ResumeState()
        assert rs.branch is None
        assert rs.progress_doc is None
