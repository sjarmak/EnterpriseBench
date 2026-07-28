from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for import_path in (
    PROJECT_ROOT / "lib",
    PROJECT_ROOT / "scripts" / "orchestration",
    PROJECT_ROOT / "scripts" / "studies",
):
    sys.path.insert(0, str(import_path))

from eb_verify.judge.models import CheckpointJudgeResult  # noqa: E402
from headline_v4_judge_canary import (  # noqa: E402
    CanaryError,
    load_canary_plan,
    run_canary,
)


def _plan(tmp_path: Path, *, authorized: bool = True) -> Path:
    backend = tmp_path / "lib/eb_verify/judge/backends.py"
    engine = tmp_path / "lib/eb_verify/judge/engine.py"
    backend.parent.mkdir(parents=True)
    backend.write_text("backend")
    engine.write_text("engine")
    path = tmp_path / "canary.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "study_id": "rryas-headline-v4-judge-canary",
                "status": "AUTHORIZED" if authorized else "LOCKED-NO-SPEND",
                "paid_dispatch_authorized": authorized,
                "authorization_reference": "test-user-approval" if authorized else None,
                "account": 1,
                "model": "cc:haiku",
                "max_budget_usd": 0.1,
                "input_chars": 12000,
                "backend_hash": (
                    "sha256:"
                    "10e08a419e850eba1ebba18fdd28eb7ec1b7e8baa9bcc3b973e2b8891ec726be"
                ),
                "engine_hash": (
                    "sha256:"
                    "ed9f6f25068608efd412958da4dfc19328ca3511251fa6d5f9c42baf230e32f8"
                ),
                "output": "results/canary/result.json",
            }
        )
    )
    return path


def test_canary_runs_exact_isolated_judge_contract(tmp_path: Path) -> None:
    plan_path = _plan(tmp_path)
    plan = load_canary_plan(plan_path, repo_root=tmp_path)
    observed: dict[str, object] = {}

    class FakeJudge:
        provenance = {
            "backend": "claude_code_cli",
            "account": 1,
            "model": "haiku",
            "max_budget_usd": 0.1,
        }

        def evaluate_checkpoint(self, judge_input, **_kwargs):
            observed["chars"] = len(judge_input.agent_output)
            return CheckpointJudgeResult(
                checkpoint_name=judge_input.checkpoint_name,
                score=1.0,
                passed=True,
                reasoning="ok",
            )

    result = run_canary(
        plan,
        repo_root=tmp_path,
        judge_factory=lambda **_kwargs: FakeJudge(),
    )

    assert observed["chars"] == 12000
    assert result["status"] == "COMPLETE-OPERATIONAL-VALID"
    assert result["paid_inference_dispatched"] is True
    assert result["agent_inference_dispatched"] is False
    assert json.loads((tmp_path / "results/canary/result.json").read_text()) == result


def test_canary_refuses_closed_plan(tmp_path: Path) -> None:
    with pytest.raises(CanaryError, match="not authorized"):
        load_canary_plan(_plan(tmp_path, authorized=False), repo_root=tmp_path)


def test_canary_refuses_replay(tmp_path: Path) -> None:
    plan = load_canary_plan(_plan(tmp_path), repo_root=tmp_path)
    output = tmp_path / "results/canary/result.json"
    output.parent.mkdir(parents=True)
    output.write_text("{}")

    with pytest.raises(CanaryError, match="already exists"):
        run_canary(plan, repo_root=tmp_path, judge_factory=lambda **_kwargs: object())
