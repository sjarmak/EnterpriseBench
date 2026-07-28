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
    PROJECT_ROOT / "scripts" / "studies",
):
    sys.path.insert(0, str(import_path))

import authorize_headline_v3_batch  # noqa: E402
from authorize_headline_v3_batch import (  # noqa: E402
    AuthorizationError,
    build_authorized_plan,
    main,
    write_authorized_plan,
)
from headline_dispatch_policy import authorization_batch_hash  # noqa: E402
from headline_study_dispatch import compile_run_command, load_dispatch_plan  # noqa: E402
from tests.test_headline_study_dispatch import _write_fixture  # noqa: E402


def test_build_authorized_plan_binds_one_exact_pending_batch(
    tmp_path: Path,
) -> None:
    plan_path, *_ = _write_fixture(tmp_path, study_id="rryas-headline-v3")

    payload = build_authorized_plan(
        plan_path=plan_path,
        repo_root=tmp_path,
        authorization_reference="user-approved-test-batch",
        capacity_reference="account-3-reset-confirmed",
    )

    assert payload["provider_capacity"] == {
        "confirmed": True,
        "capacity_reference": "account-3-reset-confirmed",
        "confirmed_completed_prefix": 0,
        "confirmed_max_slots": 12,
    }
    assert payload["authorization"]["paid_dispatch_authorized"] is True
    assert payload["authorization"]["authorized_completed_prefix"] == 0
    assert payload["authorization"]["authorized_end_prefix"] == 6
    assert payload["authorization"]["authorized_outer_spend_ceiling_usd"] == 60.0

    authorized_path = tmp_path / "dispatch_plan.authorized-test.json"
    write_authorized_plan(authorized_path, payload)
    plan = load_dispatch_plan(authorized_path, repo_root=tmp_path)
    commands = tuple(
        compile_run_command(slot, plan=plan, repo_root=tmp_path)
        for slot in plan.slots
    )
    assert plan.v3_controls is not None
    assert plan.v3_controls.authorized_batch_hash == authorization_batch_hash(
        plan,
        commands,
        start_prefix=0,
        end_prefix=6,
    )


@pytest.mark.parametrize(
    ("authorization_reference", "capacity_reference"),
    (("", "capacity"), ("approval", "  ")),
)
def test_authorizer_rejects_blank_attestations(
    tmp_path: Path,
    authorization_reference: str,
    capacity_reference: str,
) -> None:
    plan_path, *_ = _write_fixture(tmp_path, study_id="rryas-headline-v3")

    with pytest.raises(AuthorizationError, match="non-blank"):
        build_authorized_plan(
            plan_path=plan_path,
            repo_root=tmp_path,
            authorization_reference=authorization_reference,
            capacity_reference=capacity_reference,
        )


def test_authorizer_never_overwrites_an_existing_artifact(tmp_path: Path) -> None:
    output = tmp_path / "dispatch_plan.authorized-test.json"
    output.write_text(json.dumps({"existing": True}))

    with pytest.raises(AuthorizationError, match="already exists"):
        write_authorized_plan(output, {"replacement": True})

    assert json.loads(output.read_text()) == {"existing": True}


def test_authorizer_cli_writes_loadable_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan_path, *_ = _write_fixture(tmp_path, study_id="rryas-headline-v3")
    output = plan_path.with_name("dispatch_plan.authorized-test.json")
    monkeypatch.setattr(authorize_headline_v3_batch, "REPO_ROOT", tmp_path)

    result = main(
        [
            "--plan",
            str(plan_path),
            "--output",
            str(output),
            "--authorization-reference",
            "user-approved-test-batch",
            "--capacity-reference",
            "account-3-reset-confirmed",
        ]
    )

    assert result == 0
    assert load_dispatch_plan(output, repo_root=tmp_path).paid_dispatch_authorized
    summary = json.loads(capsys.readouterr().out)
    assert summary["authorized_completed_prefix"] == 0
    assert summary["authorized_end_prefix"] == 6


def test_authorizer_cli_rejects_output_outside_capsule(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan_path, *_ = _write_fixture(tmp_path, study_id="rryas-headline-v3")
    monkeypatch.setattr(authorize_headline_v3_batch, "REPO_ROOT", tmp_path)

    with pytest.raises(SystemExit, match="2"):
        main(
            [
                "--plan",
                str(plan_path),
                "--output",
                str(tmp_path / "other" / "authorized.json"),
                "--authorization-reference",
                "user-approved-test-batch",
                "--capacity-reference",
                "account-3-reset-confirmed",
            ]
        )

    assert "must share the capsule directory" in capsys.readouterr().err


def test_authorizer_rejects_malformed_base_plan(tmp_path: Path) -> None:
    plan_path = tmp_path / "dispatch_plan.json"
    plan_path.write_text("{")

    with pytest.raises(AuthorizationError, match="not valid JSON"):
        build_authorized_plan(
            plan_path=plan_path,
            repo_root=tmp_path,
            authorization_reference="user-approved-test-batch",
            capacity_reference="account-3-reset-confirmed",
        )
