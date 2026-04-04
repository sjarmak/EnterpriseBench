"""Tests for the Phase 1 pilot orchestrator."""

import csv
import json
import tempfile
from pathlib import Path

import pytest

# Import from the orchestrator module
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "orchestration"))

from run_pilot import (
    REQUIRED_FIELDS,
    RunEntry,
    RunResult,
    is_ablation_run,
    load_manifest,
    validate_output_paths,
    write_run_manifest,
    write_summary_csv,
)

PILOT_MANIFEST = REPO_ROOT / "configs" / "pilot_manifest.json"


class TestManifestLoading:
    """Tests for manifest loading and validation."""

    def test_load_manifest_returns_list(self) -> None:
        entries = load_manifest(PILOT_MANIFEST)
        assert isinstance(entries, list)

    def test_manifest_has_exactly_48_entries(self) -> None:
        entries = load_manifest(PILOT_MANIFEST)
        assert len(entries) == 48

    def test_all_entries_are_run_entry(self) -> None:
        entries = load_manifest(PILOT_MANIFEST)
        for entry in entries:
            assert isinstance(entry, RunEntry)

    def test_all_required_fields_present(self) -> None:
        raw = json.loads(PILOT_MANIFEST.read_text())
        for i, item in enumerate(raw):
            missing = REQUIRED_FIELDS - set(item.keys())
            assert not missing, f"Entry {i} missing: {missing}"

    def test_load_missing_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_manifest(Path("/nonexistent/manifest.json"))

    def test_load_invalid_json_raises(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not json")
            f.flush()
            with pytest.raises(json.JSONDecodeError):
                load_manifest(Path(f.name))

    def test_load_non_array_raises(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"entries": []}, f)
            f.flush()
            with pytest.raises(ValueError, match="JSON array"):
                load_manifest(Path(f.name))

    def test_missing_field_raises(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([{"task_id": "test"}], f)
            f.flush()
            with pytest.raises(ValueError, match="missing fields"):
                load_manifest(Path(f.name))


class TestManifestStructure:
    """Tests for manifest entry structure and content."""

    def test_task_ids_are_expected(self) -> None:
        entries = load_manifest(PILOT_MANIFEST)
        task_ids = {e.task_id for e in entries}
        expected = {
            "incident-inv-docker-shutdown-004",
            "error-trace-k8s-nftables-sync-001",
            "support-map-grafana-alerts-004",
            "config-drift-argocd-redis-ha-004",
        }
        assert task_ids == expected

    def test_full_run_modes(self) -> None:
        entries = load_manifest(PILOT_MANIFEST)
        full_modes = {e.mode for e in entries if not e.mode.startswith("ablate-")}
        assert full_modes == {"baseline", "mcp_only", "hybrid"}

    def test_ablation_modes(self) -> None:
        entries = load_manifest(PILOT_MANIFEST)
        ablation_modes = {e.mode for e in entries if e.mode.startswith("ablate-")}
        expected = {
            "ablate-moby",
            "ablate-containerd",
            "ablate-grafana",
            "ablate-alertmanager",
        }
        assert ablation_modes == expected

    def test_rep_indices_are_1_to_3(self) -> None:
        entries = load_manifest(PILOT_MANIFEST)
        rep_indices = {e.rep_index for e in entries}
        assert rep_indices == {1, 2, 3}

    def test_account_ids_are_1_to_5(self) -> None:
        entries = load_manifest(PILOT_MANIFEST)
        account_ids = {e.account_id for e in entries}
        assert account_ids == {1, 2, 3, 4, 5}

    def test_36_full_runs(self) -> None:
        entries = load_manifest(PILOT_MANIFEST)
        full_runs = [e for e in entries if not e.mode.startswith("ablate-")]
        assert len(full_runs) == 36

    def test_12_ablation_runs(self) -> None:
        entries = load_manifest(PILOT_MANIFEST)
        ablation_runs = [e for e in entries if e.mode.startswith("ablate-")]
        assert len(ablation_runs) == 12

    def test_ablation_tasks_are_correct(self) -> None:
        entries = load_manifest(PILOT_MANIFEST)
        ablation_task_ids = {e.task_id for e in entries if e.mode.startswith("ablate-")}
        expected = {
            "incident-inv-docker-shutdown-004",
            "support-map-grafana-alerts-004",
        }
        assert ablation_task_ids == expected


class TestAccountRoundRobin:
    """Tests for round-robin account assignment."""

    def test_account_ids_cycle_1_to_5(self) -> None:
        entries = load_manifest(PILOT_MANIFEST)
        for i, entry in enumerate(entries):
            expected_account = (i % 5) + 1
            assert entry.account_id == expected_account, (
                f"Entry {i} ({entry.task_id}/{entry.mode}/rep{entry.rep_index}): "
                f"expected account_id={expected_account}, got {entry.account_id}"
            )

    def test_each_account_gets_runs(self) -> None:
        entries = load_manifest(PILOT_MANIFEST)
        for account_id in range(1, 6):
            count = sum(1 for e in entries if e.account_id == account_id)
            assert count > 0, f"Account {account_id} has no runs"


class TestOutputPaths:
    """Tests for output path generation and validation."""

    def test_output_paths_follow_convention(self) -> None:
        entries = load_manifest(PILOT_MANIFEST)
        validate_output_paths(entries)  # Raises on mismatch

    def test_full_run_path_pattern(self) -> None:
        entries = load_manifest(PILOT_MANIFEST)
        for entry in entries:
            if not entry.mode.startswith("ablate-"):
                expected = (
                    f"results/runs/{entry.task_id}/{entry.mode}/rep{entry.rep_index}/"
                )
                assert entry.output_dir == expected

    def test_ablation_run_path_pattern(self) -> None:
        entries = load_manifest(PILOT_MANIFEST)
        for entry in entries:
            if entry.mode.startswith("ablate-"):
                excluded_repo = entry.mode.removeprefix("ablate-")
                expected = f"results/runs/{entry.task_id}/ablate-{excluded_repo}/rep{entry.rep_index}/"
                assert entry.output_dir == expected

    def test_no_duplicate_output_dirs(self) -> None:
        entries = load_manifest(PILOT_MANIFEST)
        output_dirs = [e.output_dir for e in entries]
        assert len(output_dirs) == len(
            set(output_dirs)
        ), "Duplicate output directories found"


class TestAblationDetection:
    """Tests for ablation run detection."""

    def test_ablation_run_detected(self) -> None:
        entry = RunEntry(
            task_id="test",
            task_dir="benchmarks/test",
            mode="ablate-moby",
            rep_index=1,
            account_id=1,
            output_dir="results/runs/test/ablate-moby/rep1/",
        )
        assert is_ablation_run(entry) is True

    def test_full_run_not_ablation(self) -> None:
        entry = RunEntry(
            task_id="test",
            task_dir="benchmarks/test",
            mode="baseline",
            rep_index=1,
            account_id=1,
            output_dir="results/runs/test/baseline/rep1/",
        )
        assert is_ablation_run(entry) is False


class TestRunManifestCreation:
    """Tests for run manifest JSON output."""

    def test_write_run_manifest(self, tmp_path: Path) -> None:
        results = [
            RunResult(
                task_id="test-task",
                mode="baseline",
                rep_index=1,
                account_id=1,
                output_dir="results/runs/test-task/baseline/rep1/",
                status="completed",
                score=0.85,
            ),
            RunResult(
                task_id="test-task",
                mode="baseline",
                rep_index=2,
                account_id=2,
                output_dir="results/runs/test-task/baseline/rep2/",
                status="failed",
                error="timeout",
            ),
        ]

        output_path = tmp_path / "run_manifest.json"
        write_run_manifest(results, output_path)

        assert output_path.is_file()
        data = json.loads(output_path.read_text())
        assert data["total_runs"] == 2
        assert data["by_status"]["completed"] == 1
        assert data["by_status"]["failed"] == 1
        assert len(data["entries"]) == 2

    def test_run_manifest_has_generated_at(self, tmp_path: Path) -> None:
        results = [
            RunResult(
                task_id="t",
                mode="baseline",
                rep_index=1,
                account_id=1,
                output_dir="results/runs/t/baseline/rep1/",
                status="dry-run",
            ),
        ]
        output_path = tmp_path / "run_manifest.json"
        write_run_manifest(results, output_path)

        data = json.loads(output_path.read_text())
        assert "generated_at" in data


class TestSummaryCSV:
    """Tests for summary CSV output."""

    def test_write_summary_csv(self, tmp_path: Path) -> None:
        results = [
            RunResult(
                task_id="task-1",
                mode="baseline",
                rep_index=1,
                account_id=1,
                output_dir="results/runs/task-1/baseline/rep1/",
                status="completed",
                score=0.9,
            ),
        ]

        output_path = tmp_path / "summary.csv"
        write_summary_csv(results, output_path)

        assert output_path.is_file()
        with output_path.open() as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["task_id"] == "task-1"
        assert rows[0]["status"] == "completed"
        assert rows[0]["score"] == "0.9"

    def test_csv_headers(self, tmp_path: Path) -> None:
        results = [
            RunResult(
                task_id="t",
                mode="mcp_only",
                rep_index=1,
                account_id=2,
                output_dir="results/runs/t/mcp_only/rep1/",
                status="dry-run",
            ),
        ]
        output_path = tmp_path / "summary.csv"
        write_summary_csv(results, output_path)

        with output_path.open() as f:
            reader = csv.DictReader(f)
            assert set(reader.fieldnames) == {
                "task_id",
                "mode",
                "rep_index",
                "account_id",
                "status",
                "score",
                "error",
            }


class TestDryRun:
    """Tests for dry-run mode."""

    def test_dry_run_entry_produces_dry_run_status(self) -> None:
        from run_pilot import execute_run

        entry = RunEntry(
            task_id="test-task",
            task_dir="benchmarks/test",
            mode="baseline",
            rep_index=1,
            account_id=1,
            output_dir="results/runs/test-task/baseline/rep1/",
        )
        result = execute_run(entry, dry_run=True)
        assert result.status == "dry-run"
        assert result.task_id == "test-task"
        assert result.score is None

    def test_dry_run_does_not_create_output_dir(self, tmp_path: Path) -> None:
        from run_pilot import execute_run

        output_dir = str(tmp_path / "should_not_exist" / "baseline" / "rep1") + "/"
        entry = RunEntry(
            task_id="test-task",
            task_dir="benchmarks/test",
            mode="baseline",
            rep_index=1,
            account_id=1,
            output_dir=output_dir,
        )
        execute_run(entry, dry_run=True)
        assert not (tmp_path / "should_not_exist").exists()


class TestFrozenDataclasses:
    """Tests that data structures are immutable."""

    def test_run_entry_is_frozen(self) -> None:
        entry = RunEntry(
            task_id="t",
            task_dir="d",
            mode="baseline",
            rep_index=1,
            account_id=1,
            output_dir="o",
        )
        with pytest.raises(AttributeError):
            entry.task_id = "modified"  # type: ignore[misc]

    def test_run_result_is_frozen(self) -> None:
        result = RunResult(
            task_id="t",
            mode="baseline",
            rep_index=1,
            account_id=1,
            output_dir="o",
        )
        with pytest.raises(AttributeError):
            result.status = "modified"  # type: ignore[misc]
