from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for import_path in (
    PROJECT_ROOT / "lib",
    PROJECT_ROOT / "scripts" / "infra",
    PROJECT_ROOT / "scripts" / "orchestration",
):
    sys.path.insert(0, str(import_path))

import headline_study_preflight as preflight_module  # noqa: E402
from eb_study import file_hash  # noqa: E402
from headline_study_preflight import (  # noqa: E402
    POST_LOCK_EXPOSURES,
    REQUIRED_ANALYSIS_PLAN,
    REQUIRED_ARMS,
    REQUIRED_CACHE_ISOLATION,
    REQUIRED_EXECUTION_BASE,
    REQUIRED_JUDGE,
    REQUIRED_SELECTION_RULE,
    STUDY_ID,
    validate_headline_study,
)
from study_run import InputProvenance  # noqa: E402


def _task_toml(task_id: str, index: int) -> str:
    return f"""
difficulty_stratum = "dual_repo"

[task]
id = "{task_id}"
suite = "dependency_management"
task_type = "dependency_graph"
estimated_duration_minutes = 30
prompt = "Trace the dependency and write a report."

[[repos]]
url = "https://github.com/example/repo-{index:02d}-a"
rev = "v1.0.0"
path = "repo-{index:02d}-a"
role = "primary"

[[repos]]
url = "https://github.com/example/repo-{index:02d}-b"
rev = "v2.0.0"
path = "repo-{index:02d}-b"
role = "dependency"

[[checkpoints]]
name = "trace"
weight = 1.0
verifier = "checks/check_trace.sh"

[artifacts]
required = ["answer"]
"""


def _execution_order(tasks: list[dict[str, object]]) -> list[dict[str, object]]:
    arm_rotations = (
        ("baseline", "mcp_only", "cli"),
        ("mcp_only", "cli", "baseline"),
        ("cli", "baseline", "mcp_only"),
    )
    rows: list[dict[str, object]] = []
    for index, task in enumerate(tasks):
        for arm in arm_rotations[index % len(arm_rotations)]:
            task_id = str(task["task_id"])
            rows.append(
                {
                    "candidate_id": task["candidate_id"],
                    "task_id": task_id,
                    "arm": arm,
                    "repetition": 1,
                    "attempt": 1,
                    "agent_account": 3,
                    "judge_account": 1,
                    "output_dir": (
                        f"results/studies/{STUDY_ID}/runs/{task_id}/{arm}/rep1/attempt1"
                    ),
                }
            )
    return rows


def _write_fixture(
    tmp_path: Path,
) -> tuple[Path, Path, Path, Path, dict[str, InputProvenance]]:
    selected_candidate_ids = [f"candidate-{index:02d}" for index in range(43)]
    candidate_ids = [*selected_candidate_ids, *POST_LOCK_EXPOSURES]
    candidate_manifest = tmp_path / "candidate_manifest.json"
    candidate_manifest.write_text(
        json.dumps(
            {
                "status": "CANDIDATE",
                "count": 48,
                "task_ids": candidate_ids,
            }
        )
    )

    tasks: list[dict[str, object]] = []
    provenances: dict[str, InputProvenance] = {}
    for index, candidate_id in enumerate(selected_candidate_ids):
        task_id = f"canonical-task-{index:02d}" if index < 2 else candidate_id
        task_dir = tmp_path / "benchmarks" / "suite" / candidate_id
        checks = task_dir / "checks"
        checks.mkdir(parents=True)
        task_toml = task_dir / "task.toml"
        task_toml.write_text(_task_toml(task_id, index))
        (task_dir / "instruction.md").write_text(
            "Write the report to `/workspace/analysis/IMPACT_REPORT.md`.\n"
        )
        (checks / "check_trace.sh").write_text(
            "#!/usr/bin/env bash\n"
            'REPORT="${WORKSPACE:-/workspace}/analysis/IMPACT_REPORT.md"\n'
        )
        (task_dir / "expected_solution.json").write_text(
            json.dumps(
                {
                    "task_id": task_id,
                    "checkpoints": {
                        "trace": {
                            "expected_solution": "Trace both repositories.",
                            "evaluation_criteria": ["Cites both repositories"],
                        }
                    },
                }
            )
        )
        task_hash = file_hash(task_toml)
        verifier_hash = f"sha256:verifier-{index:02d}"
        provenances[task_id] = InputProvenance(
            task_hash=task_hash,
            harness_hash="sha256:harness",
            verifier_hash=verifier_hash,
        )
        tasks.append(
            {
                "candidate_id": candidate_id,
                "task_id": task_id,
                "task_type": "dependency_graph",
                "difficulty_stratum": "dual_repo",
                "task_toml": str(task_toml.relative_to(tmp_path)),
                "task_hash": task_hash,
                "graded_artifact_path": "/workspace/analysis/IMPACT_REPORT.md",
                "expected_repositories": [
                    f"github.com/sg-evals/repo-{index:02d}-a--v1.0.0",
                    f"github.com/sg-evals/repo-{index:02d}-b--v2.0.0",
                ],
            }
        )

    analysis_path = tmp_path / "analysis_plan.json"
    analysis_path.write_text(json.dumps(REQUIRED_ANALYSIS_PLAN))
    output_root = f"results/studies/{STUDY_ID}"
    manifest_path = tmp_path / "final_manifest.json"
    manifest = {
        "schema_version": 1,
        "status": "FINAL-NO-SPEND",
        "study_id": STUDY_ID,
        "purpose": "Confirmatory Claude Sonnet 5 protocol comparison.",
        "candidate_manifest": "candidate_manifest.json",
        "candidate_manifest_hash": file_hash(candidate_manifest),
        "candidate_lock_revision": preflight_module.CANDIDATE_LOCK_REVISION,
        "analysis_plan": "analysis_plan.json",
        "analysis_plan_hash": file_hash(analysis_path),
        "selection": {
            "rule": REQUIRED_SELECTION_RULE,
            "candidate_outcomes_inspected": False,
            "candidate_count": 48,
            "selected_count": 43,
            "post_lock_exposures": [
                {
                    "candidate_id": candidate_id,
                    "reason": "post_lock_agent_output",
                    "evidence": list(
                        preflight_module.POST_LOCK_EXPOSURE_EVIDENCE[candidate_id]
                    ),
                }
                for candidate_id in POST_LOCK_EXPOSURES
            ],
        },
        "tasks": tasks,
        "arms": {
            "baseline": "local repositories; no Sourcegraph",
            "mcp_only": "Sourcegraph MCP; local repositories denied",
            "cli": "Sourcegraph CLI; local repositories readable; CLI use required",
        },
        "cache_isolation": REQUIRED_CACHE_ISOLATION,
        "judge_configuration": REQUIRED_JUDGE,
        "execution_configuration": {
            **REQUIRED_EXECUTION_BASE,
            "output_root": output_root,
            "receipts": f"{output_root}/receipts.jsonl",
            "order_policy": preflight_module.REQUIRED_ORDER_POLICY,
            "execution_order": _execution_order(tasks),
        },
        "spend_guard": {
            "slots": 129,
            "max_attempts_per_slot": 1,
            "paid_dispatch_requires_new_explicit_authorization": True,
            "paid_dispatch_authorized": False,
            "forecast_reported_outer_spend_usd": None,
            "forecast_basis": (
                "No extrapolation from confounded pilot costs; report actual "
                "provider usage before paid authorization."
            ),
        },
        "evidence_policy": preflight_module.REQUIRED_EVIDENCE_POLICY,
        "harness_hash": "sha256:harness",
        "verifier_hashes": {
            task_id: provenance.verifier_hash
            for task_id, provenance in provenances.items()
        },
    }
    manifest_path.write_text(json.dumps(manifest))

    spec_path = tmp_path / "study_spec.json"
    spec_path.write_text(
        json.dumps(
            {
                "study_id": STUDY_ID,
                "schema_version": 1,
                "task_manifest_hash": file_hash(manifest_path),
                "task_ids": [task["task_id"] for task in tasks],
                "arms": [
                    {"name": name, "capability_fingerprint": fingerprint}
                    for name, fingerprint in REQUIRED_ARMS
                ],
                "baseline_arm": "baseline",
                "repetitions": 1,
                "attempt_policy": "first_valid_attempt",
                "max_attempts": 1,
                "model": "claude-sonnet-5",
                "harness": "sha256:harness",
                "revision": "abc123",
                "token_source": "sdk_model_usage",
                "score_contract": "weighted-mean-v2",
                "promotion_policy": "paired-valid-complete-arms",
            }
        )
    )
    return spec_path, manifest_path, candidate_manifest, analysis_path, provenances


def _validate(tmp_path: Path):
    spec, manifest, candidate, analysis, provenances = _write_fixture(tmp_path)
    return validate_headline_study(
        spec_path=spec,
        manifest_path=manifest,
        candidate_manifest_path=candidate,
        analysis_plan_path=analysis,
        repo_root=tmp_path,
        revision_validator=lambda _revision, _paths: True,
        provenance_provider=lambda task_toml: provenances[
            json.loads((task_toml.parent / "expected_solution.json").read_text())[
                "task_id"
            ]
        ],
        mirror_probe=lambda _repository: True,
        auth_probe=lambda _credential: True,
    )


def test_final_capsule_compiles_43_tasks_and_129_no_retry_slots(
    tmp_path: Path,
) -> None:
    evidence = _validate(tmp_path)

    assert len(evidence.candidate_ids) == 43
    assert len(evidence.task_ids) == 43
    assert len(evidence.slots) == 129
    assert evidence.task_ids[:2] == (
        "canonical-task-00",
        "canonical-task-01",
    )
    assert evidence.paid_dispatch_authorized is False


def test_execution_order_rotates_arms_and_has_unique_outputs(tmp_path: Path) -> None:
    spec, manifest_path, candidate, analysis, provenances = _write_fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    order = manifest["execution_configuration"]["execution_order"]

    assert [row["arm"] for row in order[:9]] == [
        "baseline",
        "mcp_only",
        "cli",
        "mcp_only",
        "cli",
        "baseline",
        "cli",
        "baseline",
        "mcp_only",
    ]
    assert len({row["output_dir"] for row in order}) == 129

    evidence = validate_headline_study(
        spec_path=spec,
        manifest_path=manifest_path,
        candidate_manifest_path=candidate,
        analysis_plan_path=analysis,
        repo_root=tmp_path,
        revision_validator=lambda _revision, _paths: True,
        provenance_provider=lambda task_toml: provenances[
            json.loads((task_toml.parent / "expected_solution.json").read_text())[
                "task_id"
            ]
        ],
        mirror_probe=lambda _repository: True,
        auth_probe=lambda _credential: True,
    )
    assert evidence.output_root == f"results/studies/{STUDY_ID}"
    assert manifest["execution_configuration"]["no_build"] is False


def test_headline_mirror_scope_supports_more_than_two_repositories() -> None:
    mirrors = preflight_module._expected_headline_mirrors(
        {
            "repos": [
                {"url": "https://github.com/acme/one", "rev": "v1.0.0"},
                {"url": "https://github.com/acme/two", "rev": "v2.0.0"},
                {"url": "https://github.com/acme/three", "rev": "v3.0.0"},
                {"url": "https://github.com/acme/four", "rev": "v4.0.0"},
            ]
        }
    )

    assert mirrors == (
        "github.com/sg-evals/one--v1.0.0",
        "github.com/sg-evals/two--v2.0.0",
        "github.com/sg-evals/three--v3.0.0",
        "github.com/sg-evals/four--v4.0.0",
    )


@pytest.mark.parametrize(
    ("target", "mutate", "message"),
    [
        (
            "manifest",
            lambda payload: payload["selection"].update(
                {"candidate_outcomes_inspected": True}
            ),
            "outcome-blind",
        ),
        (
            "manifest",
            lambda payload: payload["selection"]["post_lock_exposures"].pop(),
            "exposure ledger",
        ),
        (
            "manifest",
            lambda payload: payload["tasks"][1].update(
                {"task_id": payload["tasks"][0]["task_id"]}
            ),
            "identity",
        ),
        (
            "manifest",
            lambda payload: payload["execution_configuration"].update(
                {"max_attempts": 2}
            ),
            "execution contract",
        ),
        (
            "analysis",
            lambda payload: payload["inference"].update({"bootstrap_repetitions": 100}),
            "analysis plan",
        ),
    ],
)
def test_protocol_drift_fails_closed(
    tmp_path: Path,
    target: str,
    mutate,
    message: str,
) -> None:
    spec_path, manifest_path, candidate, analysis_path, provenances = _write_fixture(
        tmp_path
    )
    path = manifest_path if target == "manifest" else analysis_path
    payload = json.loads(path.read_text())
    mutate(payload)
    path.write_text(json.dumps(payload))
    if target == "manifest":
        spec = json.loads(spec_path.read_text())
        spec["task_manifest_hash"] = file_hash(manifest_path)
        spec_path.write_text(json.dumps(spec))

    with pytest.raises(ValueError, match=message):
        validate_headline_study(
            spec_path=spec_path,
            manifest_path=manifest_path,
            candidate_manifest_path=candidate,
            analysis_plan_path=analysis_path,
            repo_root=tmp_path,
            revision_validator=lambda _revision, _paths: True,
            provenance_provider=lambda task_toml: provenances[
                json.loads((task_toml.parent / "expected_solution.json").read_text())[
                    "task_id"
                ]
            ],
            mirror_probe=lambda _repository: True,
            auth_probe=lambda _credential: True,
        )


def test_unavailable_mirror_fails_closed(tmp_path: Path) -> None:
    spec, manifest, candidate, analysis, provenances = _write_fixture(tmp_path)

    with pytest.raises(ValueError, match="Sourcegraph mirror is unavailable"):
        validate_headline_study(
            spec_path=spec,
            manifest_path=manifest,
            candidate_manifest_path=candidate,
            analysis_plan_path=analysis,
            repo_root=tmp_path,
            revision_validator=lambda _revision, _paths: True,
            provenance_provider=lambda task_toml: provenances[
                json.loads((task_toml.parent / "expected_solution.json").read_text())[
                    "task_id"
                ]
            ],
            mirror_probe=lambda repository: (
                not repository.endswith("repo-05-b--v2.0.0")
            ),
            auth_probe=lambda _credential: True,
        )


def test_missing_agent_or_judge_auth_fails_closed(tmp_path: Path) -> None:
    spec, manifest, candidate, analysis, provenances = _write_fixture(tmp_path)

    with pytest.raises(ValueError, match="Claude agent account 3"):
        validate_headline_study(
            spec_path=spec,
            manifest_path=manifest,
            candidate_manifest_path=candidate,
            analysis_plan_path=analysis,
            repo_root=tmp_path,
            revision_validator=lambda _revision, _paths: True,
            provenance_provider=lambda task_toml: provenances[
                json.loads((task_toml.parent / "expected_solution.json").read_text())[
                    "task_id"
                ]
            ],
            mirror_probe=lambda _repository: True,
            auth_probe=lambda credential: credential != "agent-account-3",
        )


def test_nonempty_output_root_fails_closed(tmp_path: Path) -> None:
    spec, manifest, candidate, analysis, provenances = _write_fixture(tmp_path)
    output_root = tmp_path / "results" / "studies" / STUDY_ID
    output_root.mkdir(parents=True)
    (output_root / "foreign-run.json").write_text("{}")

    with pytest.raises(ValueError, match="output root is not clean"):
        validate_headline_study(
            spec_path=spec,
            manifest_path=manifest,
            candidate_manifest_path=candidate,
            analysis_plan_path=analysis,
            repo_root=tmp_path,
            revision_validator=lambda _revision, _paths: True,
            provenance_provider=lambda task_toml: provenances[
                json.loads((task_toml.parent / "expected_solution.json").read_text())[
                    "task_id"
                ]
            ],
            mirror_probe=lambda _repository: True,
            auth_probe=lambda _credential: True,
        )
