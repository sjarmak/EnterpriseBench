"""Tests for enriched results directory structure in run_task.py.

Verifies that task runs produce:
  results.json       — top-level results (existing)
  config.json        — snapshot of run configuration
  task_metrics.json   — timing, tool_usage, status for skip-completed
  agent/stdout.log    — agent stdout (moved from flat)
  agent/stderr.log    — agent stderr (moved from flat)
  verifier/output.json — verifier scoring output
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Make scripts importable
sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "scripts" / "orchestration")
)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "infra"))

import run_task as run_task_module
from eb_study import read_receipts
from run_task import (
    TaskRunConfig,
    TaskRunResult,
    _capture_arm_gate_proof,
    _capture_input_provenance,
    _docker_image_digest,
    _save_results,
)
from study_run import capture_input_provenance, docker_container_image_digest
from tests.test_study_capsule import make_spec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_task_data(task_id: str = "test-enrich-001") -> dict:
    return {
        "task": {
            "id": task_id,
            "suite": "customer_escalation",
            "task_type": "error_provenance",
            "difficulty": "medium",
            "session_type": "single",
        },
        "metadata": {
            "languages": ["python"],
        },
    }


def _make_config(**overrides) -> TaskRunConfig:
    defaults = dict(
        task_toml=Path("/fake/task.toml"),
        source="mirror",
        agent_command="claude -p",
        timeout=300,
        build_timeout=600,
        verifier_timeout=120,
        memory_mb=8192,
        output_dir=None,
        dry_run=False,
        no_build=False,
        keep_container=False,
        verbose=False,
        account=None,
        mode="baseline",
    )
    defaults.update(overrides)
    return TaskRunConfig(**defaults)


def _make_result(task_id: str = "test-enrich-001", **overrides) -> TaskRunResult:
    defaults = dict(
        task_id=task_id,
        phase="complete",
        success=True,
        error="",
        image_tag="eb-test-enrich-001",
        container_id="abc123",
        scores={
            "task_score": 2.5,
            "all_passed": True,
            "checkpoints_passed": 2,
            "checkpoints_total": 2,
        },
        timing={
            "parse": 0.01,
            "build": 5.0,
            "setup": 1.2,
            "agent": 120.5,
            "scoring": 0.3,
        },
        output_dir="",
        tool_usage={
            "total_input_tokens": 1000,
            "total_output_tokens": 500,
            "cost_usd": 0.05,
            "num_turns": 3,
            "mcp_tool_calls": 0,
        },
    )
    defaults.update(overrides)
    return TaskRunResult(**defaults)


# ---------------------------------------------------------------------------
# config.json
# ---------------------------------------------------------------------------


class TestConfigJsonSnapshot:
    def test_config_json_created(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "results"
        config = _make_config()
        result = _make_result()
        task_data = _make_task_data()

        _save_results(result, task_data, output_dir, config)

        config_path = output_dir / "config.json"
        assert config_path.exists(), "config.json should be created"

    def test_config_json_contains_run_settings(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "results"
        config = _make_config(
            source="upstream",
            agent_command="claude --max-turns 10 -p",
            timeout=600,
            memory_mb=4096,
            mode="mcp_only",
            judge_model="cc:haiku",
            judge_account=3,
        )
        result = _make_result()
        task_data = _make_task_data()

        _save_results(result, task_data, output_dir, config)

        data = json.loads((output_dir / "config.json").read_text())
        assert data["source"] == "upstream"
        assert data["agent_command"] == "claude --max-turns 10 -p"
        assert data["timeout"] == 600
        assert data["memory_mb"] == 4096
        assert data["mode"] == "mcp_only"
        assert data["judge_model"] == "cc:haiku"
        assert data["judge_account"] == 3

    def test_config_json_excludes_sensitive_fields(self, tmp_path: Path) -> None:
        """config.json should not contain file paths or account numbers."""
        output_dir = tmp_path / "results"
        config = _make_config(account=3)
        result = _make_result()
        task_data = _make_task_data()

        _save_results(result, task_data, output_dir, config)

        data = json.loads((output_dir / "config.json").read_text())
        # account number is fine to log (not a secret), but task_toml path is host-specific
        assert "task_toml" not in data


# ---------------------------------------------------------------------------
# task_metrics.json
# ---------------------------------------------------------------------------


class TestTaskMetricsJson:
    def test_host_attempt_clock_is_persisted_in_both_receipts(
        self, tmp_path: Path
    ) -> None:
        output_dir = tmp_path / "results"
        result = _make_result(started_at="2026-07-25T12:00:00+00:00")

        _save_results(result, _make_task_data(), output_dir, _make_config())

        results = json.loads((output_dir / "results.json").read_text())
        metrics = json.loads((output_dir / "task_metrics.json").read_text())
        assert results["started_at"] == "2026-07-25T12:00:00+00:00"
        assert metrics["started_at"] == results["started_at"]
        assert results["completed_at"] == metrics["completed_at"]
        assert results["completed_at"] > results["started_at"]

    def test_task_metrics_created(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "results"
        config = _make_config()
        result = _make_result()
        task_data = _make_task_data()

        _save_results(result, task_data, output_dir, config)

        metrics_path = output_dir / "task_metrics.json"
        assert metrics_path.exists(), "task_metrics.json should be created"

    def test_task_metrics_contains_timing(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "results"
        config = _make_config()
        result = _make_result(timing={"parse": 0.01, "agent": 55.3, "scoring": 0.2})
        task_data = _make_task_data()

        _save_results(result, task_data, output_dir, config)

        data = json.loads((output_dir / "task_metrics.json").read_text())
        assert data["timing"]["parse"] == pytest.approx(0.01)
        assert data["timing"]["agent"] == pytest.approx(55.3)

    def test_task_metrics_contains_tool_usage(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "results"
        config = _make_config()
        result = _make_result(tool_usage={"total_input_tokens": 2000, "cost_usd": 0.10})
        task_data = _make_task_data()

        _save_results(result, task_data, output_dir, config)

        data = json.loads((output_dir / "task_metrics.json").read_text())
        assert data["tool_usage"]["total_input_tokens"] == 2000
        assert data["tool_usage"]["cost_usd"] == pytest.approx(0.10)

    def test_task_metrics_contains_status(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "results"
        config = _make_config()
        result = _make_result(success=True, phase="complete")
        task_data = _make_task_data()

        _save_results(result, task_data, output_dir, config)

        data = json.loads((output_dir / "task_metrics.json").read_text())
        assert data["success"] is True
        assert data["phase"] == "complete"
        assert data["task_id"] == "test-enrich-001"

    def test_task_metrics_on_error(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "results"
        config = _make_config()
        result = _make_result(
            success=False,
            phase="build_failed",
            error="Docker build failed",
            failure_class="infra_build",
        )
        task_data = _make_task_data()

        _save_results(result, task_data, output_dir, config)

        data = json.loads((output_dir / "task_metrics.json").read_text())
        assert data["success"] is False
        assert data["phase"] == "build_failed"
        assert data["failure_class"] == "infra_build"


class TestStudyReceiptIntegration:
    def test_study_config_requires_a_complete_trial_identity(self) -> None:
        with pytest.raises(ValueError, match="study_spec and study_receipts"):
            _make_config(study_spec=Path("/spec.json"))
        with pytest.raises(ValueError, match="rep"):
            _make_config(
                study_spec=Path("/spec.json"),
                study_receipts=Path("/receipts.jsonl"),
                attempt=1,
            )
        with pytest.raises(ValueError, match="does not exist"):
            _make_config(
                study_spec=Path("/missing-spec.json"),
                study_receipts=Path("/receipts.jsonl"),
                rep=1,
                attempt=1,
            )

    def test_study_config_rejects_a_stale_score_contract(self, tmp_path: Path) -> None:
        spec = make_spec(
            study_id="stale-contract",
            task_ids=["test-enrich-001"],
            repetitions=1,
            max_attempts=1,
            score_contract="legacy-v1",
        )
        spec_path = tmp_path / "study_spec.json"
        spec_path.write_text(json.dumps(spec.to_json()))

        with pytest.raises(ValueError, match="score_contract"):
            _make_config(
                study_spec=spec_path,
                study_receipts=tmp_path / "receipts.jsonl",
                rep=1,
                attempt=1,
            )

    @pytest.mark.parametrize(
        ("overrides", "message"),
        [
            ({"attempt": 1}, "attempt requires"),
            ({"attempt": None}, "attempt"),
            ({"dry_run": True}, "dry_run"),
            ({"rep": 2}, "exceeds study repetitions"),
            ({"attempt": 2}, "exceeds study max_attempts"),
        ],
    )
    def test_study_config_rejects_invalid_trial_bounds(
        self, tmp_path: Path, overrides: dict, message: str
    ) -> None:
        spec = make_spec(
            study_id="bounds",
            task_ids=["test-enrich-001"],
            repetitions=1,
            max_attempts=1,
        )
        spec_path = tmp_path / "study_spec.json"
        spec_path.write_text(json.dumps(spec.to_json()))
        values = {
            "study_spec": spec_path,
            "study_receipts": tmp_path / "receipts.jsonl",
            "rep": 1,
            "attempt": 1,
        }
        if overrides == {"attempt": 1}:
            values = {}
        values.update(overrides)

        with pytest.raises(ValueError, match=message):
            _make_config(**values)

    def test_study_config_rejects_bad_receipt_log_and_missing_parent(
        self, tmp_path: Path
    ) -> None:
        spec = make_spec(
            study_id="bad-log",
            task_ids=["test-enrich-001"],
            repetitions=1,
            max_attempts=1,
        )
        spec_path = tmp_path / "study_spec.json"
        spec_path.write_text(json.dumps(spec.to_json()))
        with pytest.raises(ValueError, match="parent does not exist"):
            _make_config(
                study_spec=spec_path,
                study_receipts=tmp_path / "missing" / "receipts.jsonl",
                rep=1,
                attempt=1,
            )

        receipts_path = tmp_path / "receipts.jsonl"
        receipts_path.write_text("not-json\n")
        with pytest.raises(ValueError, match="invalid study capsule"):
            _make_config(
                study_spec=spec_path,
                study_receipts=receipts_path,
                rep=1,
                attempt=1,
            )

    def test_save_results_appends_one_live_receipt_idempotently(
        self, tmp_path: Path
    ) -> None:
        task_id = "test-enrich-001"
        spec = make_spec(
            study_id="receipt-integration",
            task_ids=[task_id],
            repetitions=1,
            max_attempts=1,
        )
        spec_path = tmp_path / "study_spec.json"
        spec_path.write_text(json.dumps(spec.to_json()))
        receipts_path = tmp_path / "receipts.jsonl"
        output_dir = tmp_path / "run"
        output_dir.mkdir()
        (output_dir / "agent_stdout.log").write_text(
            json.dumps(
                {
                    "total_cost_usd": 0.25,
                    "modelUsage": {
                        "claude-test": {
                            "inputTokens": 10,
                            "outputTokens": 5,
                            "costUSD": 0.25,
                        }
                    },
                }
            )
        )
        result = _make_result(
            task_id=task_id,
            image_digest="sha256:" + "a" * 64,
            arm_gate_proof="mode_gate:v1:baseline:agent-readable,scorer-readable",
            task_hash="sha256:" + "b" * 64,
            harness_hash="sha256:" + "c" * 64,
            verifier_hash="sha256:" + "d" * 64,
            scores={
                "task_score": 0.75,
                "score_contract_version": 2,
                "checkpoints": [
                    {"name": "one", "weight": 0.5, "score": 1.0},
                    {"name": "two", "weight": 0.5, "score": 0.5},
                ],
            },
        )
        config = _make_config(
            mode="baseline",
            rep=1,
            attempt=1,
            study_spec=spec_path,
            study_receipts=receipts_path,
        )

        _save_results(result, _make_task_data(task_id), output_dir, config)
        _save_results(result, _make_task_data(task_id), output_dir, config)

        receipts = read_receipts(receipts_path)
        assert len(receipts) == 1
        assert receipts[0].trial.key.endswith(f"/{task_id}/baseline/rep1/att1")
        assert receipts[0].score == pytest.approx(0.75)
        persisted = json.loads((output_dir / "results.json").read_text())
        assert persisted["provenance"]["image_digest"] == result.image_digest

    def test_invalid_early_result_emits_typed_receipt_without_fake_proofs(
        self, tmp_path: Path
    ) -> None:
        task_id = "test-enrich-001"
        spec = make_spec(
            study_id="invalid-receipt",
            task_ids=[task_id],
            repetitions=1,
            max_attempts=1,
        )
        spec_path = tmp_path / "study_spec.json"
        spec_path.write_text(json.dumps(spec.to_json()))
        receipts_path = tmp_path / "receipts.jsonl"
        result = _make_result(
            task_id=task_id,
            phase="build_failed",
            success=False,
            failure_class="infra_build",
        )
        config = _make_config(
            rep=1,
            attempt=1,
            study_spec=spec_path,
            study_receipts=receipts_path,
        )

        _save_results(result, _make_task_data(task_id), tmp_path / "run", config)

        receipt = read_receipts(receipts_path)[0]
        assert receipt.status == "infra_invalid"
        assert receipt.failure_class == "infra_build"
        assert receipt.image_digest is None

    def test_docker_image_id_is_captured_and_validated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *_args, **_kwargs: subprocess.CompletedProcess(
                [], 0, stdout="sha256:" + "a" * 64 + "\n", stderr=""
            ),
        )

        assert _docker_image_digest("eb-task") == "sha256:" + "a" * 64

    @pytest.mark.parametrize(
        ("returncode", "stdout", "message"),
        [
            (1, "", "inspect failed"),
            (0, "not-a-digest", "invalid image ID"),
        ],
    )
    def test_invalid_docker_image_ids_fail_closed(
        self,
        monkeypatch: pytest.MonkeyPatch,
        returncode: int,
        stdout: str,
        message: str,
    ) -> None:
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *_args, **_kwargs: subprocess.CompletedProcess(
                [], returncode, stdout=stdout, stderr="boom"
            ),
        )

        with pytest.raises(RuntimeError, match=message):
            _docker_image_digest("eb-task")

    def test_created_container_image_id_is_captured(self) -> None:
        digest = "sha256:" + "e" * 64

        assert (
            docker_container_image_digest(
                "cid",
                runner=lambda *_args, **_kwargs: subprocess.CompletedProcess(
                    [], 0, stdout=digest, stderr=""
                ),
            )
            == digest
        )

    def test_input_provenance_changes_with_verifier_bytes(self, tmp_path: Path) -> None:
        task_toml = tmp_path / "task.toml"
        task_toml.write_text('[task]\nid = "t1"\n')
        checks = tmp_path / "checks"
        checks.mkdir()
        verifier = checks / "check_one.sh"
        verifier.write_text("#!/bin/sh\nexit 0\n")
        config = _make_config(task_toml=task_toml)

        before = _capture_input_provenance(config, tmp_path)
        verifier.write_text("#!/bin/sh\nexit 1\n")
        after = _capture_input_provenance(config, tmp_path)

        assert before.task_hash.startswith("sha256:")
        assert before.harness_hash.startswith("sha256:")
        assert before.verifier_hash != after.verifier_hash

    def test_empty_or_missing_provenance_inputs_fail_closed(
        self, tmp_path: Path
    ) -> None:
        task_toml = tmp_path / "task.toml"
        task_toml.write_text('[task]\nid = "t1"\n')
        with pytest.raises(ValueError, match="contains no files"):
            capture_input_provenance(
                task_toml=task_toml,
                harness_inputs=[],
                verifier_inputs=[task_toml],
                repo_root=tmp_path,
            )

    def test_harness_manifest_hashes_source_but_ignores_bytecode(
        self, tmp_path: Path
    ) -> None:
        task_toml = tmp_path / "task.toml"
        task_toml.write_text('[task]\nid = "t1"\n')
        harness = tmp_path / "harness"
        harness.mkdir()
        source = harness / "runner.py"
        source.write_text("VALUE = 1\n")
        before = capture_input_provenance(
            task_toml=task_toml,
            harness_inputs=[harness],
            verifier_inputs=[task_toml],
            repo_root=tmp_path,
        )
        cache = harness / "__pycache__"
        cache.mkdir()
        (cache / "runner.cpython-312.pyc").write_bytes(b"generated")
        with_cache = capture_input_provenance(
            task_toml=task_toml,
            harness_inputs=[harness],
            verifier_inputs=[task_toml],
            repo_root=tmp_path,
        )
        source.write_text("VALUE = 2\n")
        changed = capture_input_provenance(
            task_toml=task_toml,
            harness_inputs=[harness],
            verifier_inputs=[task_toml],
            repo_root=tmp_path,
        )

        assert with_cache.harness_hash == before.harness_hash
        assert changed.harness_hash != before.harness_hash
        with pytest.raises(FileNotFoundError, match="does not exist"):
            capture_input_provenance(
                task_toml=task_toml,
                harness_inputs=[tmp_path / "missing.py"],
                verifier_inputs=[task_toml],
                repo_root=tmp_path,
            )

    @pytest.mark.parametrize(
        ("mode", "agent_can_read", "scorer_can_read", "expected"),
        [
            ("baseline", True, True, "agent-readable,scorer-readable"),
            ("mcp_only", False, True, "agent-denied,scorer-readable"),
        ],
    )
    def test_arm_gate_proof_records_observed_access(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mode: str,
        agent_can_read: bool,
        scorer_can_read: bool,
        expected: str,
    ) -> None:
        monkeypatch.setattr(
            "run_task.repo_dirs", lambda _task, _root: ["/workspace/repo"]
        )
        monkeypatch.setattr(
            "run_task._gate_probe_file",
            lambda _container, _repo: "/workspace/repo/file.py",
        )
        monkeypatch.setattr(
            "run_task._can_read",
            lambda _container, _path, user: (
                agent_can_read if user == "agent" else scorer_can_read
            ),
        )

        proof, error = _capture_arm_gate_proof("cid", {"repos": [{}]}, mode)

        assert error == ""
        assert expected in proof

    def test_run_task_produces_a_valid_receipt_without_paid_inference(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        task_id = "study-e2e-001"
        task_dir = tmp_path / task_id
        task_dir.mkdir()
        task_toml = task_dir / "task.toml"
        task_toml.write_text(
            f'[task]\nid = "{task_id}"\nsuite = "test"\n'
            'task_type = "error_provenance"\nsession_type = "single"\n'
        )
        spec = make_spec(
            study_id="study-e2e",
            task_ids=[task_id],
            repetitions=1,
            max_attempts=2,
        )
        spec_path = tmp_path / "study_spec.json"
        spec_path.write_text(json.dumps(spec.to_json()))
        receipts_path = tmp_path / "receipts.jsonl"
        output_dir = tmp_path / "run"

        def fake_agent(
            _container,
            _command,
            _timeout,
            run_dir,
            **_kwargs,
        ):
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "agent_stdout.log").write_text(
                json.dumps(
                    {
                        "total_cost_usd": 0.1,
                        "modelUsage": {
                            "claude-test": {
                                "inputTokens": 5,
                                "outputTokens": 2,
                                "costUSD": 0.1,
                            }
                        },
                    }
                )
            )
            return 0, 0.01

        for name, value in (
            ("_check_disk_space", True),
            ("_docker_image_digest", "sha256:" + "a" * 64),
            ("_docker_container_image_digest", "sha256:" + "a" * 64),
            ("_docker_create_container", "cid"),
            ("_docker_start", None),
            ("_setup_container", "exact injected prompt"),
            ("_run_health_check", True),
            ("_assert_agent_readable", (True, "")),
            ("_apply_mode_gate", (True, "")),
            (
                "_capture_arm_gate_proof",
                (
                    "mode_gate:v1:baseline:agent-readable,scorer-readable",
                    "",
                ),
            ),
            ("_extract_tool_usage", {}),
            ("_record_agent_trace", None),
            ("_docker_stop_rm", None),
        ):
            monkeypatch.setattr(
                run_task_module,
                name,
                (lambda result: lambda *_args, **_kwargs: result)(value),
            )
        monkeypatch.setattr(run_task_module, "_run_agent", fake_agent)
        monkeypatch.setattr(
            run_task_module,
            "_run_scoring",
            lambda *_args, **_kwargs: {
                "task_score": 1.0,
                "score_contract_version": 2,
                "checkpoints": [{"name": "one", "weight": 1.0, "score": 1.0}],
            },
        )

        result = run_task_module.run_task(
            TaskRunConfig(
                task_toml=task_toml,
                agent_command="fake-agent",
                no_build=True,
                output_dir=output_dir,
                mode="baseline",
                rep=1,
                attempt=2,
                study_spec=spec_path,
                study_receipts=receipts_path,
            )
        )

        receipt = read_receipts(receipts_path)[0]
        assert result.success
        assert Path(result.output_dir).name == "attempt2"
        assert Path(result.output_dir).parent.name == "rep1"
        assert receipt.trial.attempt == 2
        assert receipt.status == "valid"
        assert receipt.score == pytest.approx(1.0)
        assert receipt.image_digest == "sha256:" + "a" * 64
        assert (
            Path(result.output_dir, "injected_instruction.md").read_text()
            == "exact injected prompt"
        )
        assert "injected_instruction.md" in receipt.artifacts


# ---------------------------------------------------------------------------
# agent/ subdirectory
# ---------------------------------------------------------------------------


class TestAgentSubdir:
    def test_agent_subdir_created(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "results"
        config = _make_config()
        result = _make_result()
        task_data = _make_task_data()

        _save_results(result, task_data, output_dir, config)

        agent_dir = output_dir / "agent"
        assert agent_dir.is_dir(), "agent/ subdirectory should be created"


# ---------------------------------------------------------------------------
# verifier/ subdirectory
# ---------------------------------------------------------------------------


class TestVerifierSubdir:
    def test_verifier_subdir_created(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "results"
        config = _make_config()
        result = _make_result()
        task_data = _make_task_data()

        _save_results(result, task_data, output_dir, config)

        verifier_dir = output_dir / "verifier"
        assert verifier_dir.is_dir(), "verifier/ subdirectory should be created"

    def test_verifier_output_json_written(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "results"
        config = _make_config()
        result = _make_result(
            scores={"task_score": 1.5, "checkpoints_passed": 1, "checkpoints_total": 2}
        )
        task_data = _make_task_data()

        _save_results(result, task_data, output_dir, config)

        verifier_output = output_dir / "verifier" / "output.json"
        assert verifier_output.exists(), "verifier/output.json should be written"
        data = json.loads(verifier_output.read_text())
        assert data["task_score"] == pytest.approx(1.5)


# ---------------------------------------------------------------------------
# results.json backward compatibility
# ---------------------------------------------------------------------------


class TestResultsJsonBackwardCompat:
    def test_results_json_still_at_top_level(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "results"
        config = _make_config()
        result = _make_result()
        task_data = _make_task_data()

        _save_results(result, task_data, output_dir, config)

        assert (output_dir / "results.json").exists(), (
            "results.json must remain at top level"
        )

    def test_results_json_still_has_success_field(self, tmp_path: Path) -> None:
        """is_task_completed depends on results.json having 'success' field."""
        output_dir = tmp_path / "results"
        config = _make_config()
        result = _make_result(success=True)
        task_data = _make_task_data()

        _save_results(result, task_data, output_dir, config)

        data = json.loads((output_dir / "results.json").read_text())
        assert data["success"] is True
        assert "task_id" in data
        assert "scores" in data
