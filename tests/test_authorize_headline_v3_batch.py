from __future__ import annotations

import json
import sys
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
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
from headline_provider_capacity import CapacityProbeError  # noqa: E402
from headline_study_dispatch import compile_run_command, load_dispatch_plan  # noqa: E402
from tests.test_headline_study_dispatch import _write_fixture  # noqa: E402


def _write_capacity_cache(
    path: Path,
    *,
    fetched_at: datetime,
    agent_five_hour: float = 25.0,
    judge_five_hour: float = 7.0,
    agent_fetched_at: datetime | None = None,
    judge_fetched_at: datetime | None = None,
) -> Path:
    payload = {
        "fetched_at": fetched_at.isoformat(),
        "accounts": [
            {
                "name": "account1",
                "fetched_at": (judge_fetched_at or fetched_at).isoformat(),
                "five_hour": {
                    "utilization": judge_five_hour,
                    "resets_at": "2026-07-29T06:00:00+00:00",
                },
                "seven_day": {
                    "utilization": 45.0,
                    "resets_at": "2026-07-30T02:00:00+00:00",
                },
                "error": None,
            },
            {
                "name": "account3",
                "fetched_at": (agent_fetched_at or fetched_at).isoformat(),
                "five_hour": {
                    "utilization": agent_five_hour,
                    "resets_at": "2026-07-29T06:00:00+00:00",
                },
                "seven_day": {
                    "utilization": 48.0,
                    "resets_at": "2026-08-01T16:00:00+00:00",
                },
                "error": None,
            },
        ],
    }
    path.write_text(json.dumps(payload))
    return path


def _capacity_fetcher(path: Path):
    payload = json.loads(path.read_text())

    def fetch(account_number: int) -> dict[str, object]:
        for account in payload["accounts"]:
            if account["name"] == f"account{account_number}":
                return account
        return {}

    return fetch


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


def test_v4_authorizer_embeds_fresh_nonzero_capacity_telemetry(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 7, 29, 1, 1, tzinfo=timezone.utc)
    plan_path, *_ = _write_fixture(tmp_path, study_id="rryas-headline-v4")
    capacity_cache = _write_capacity_cache(
        tmp_path / "usage_cache.json",
        fetched_at=now - timedelta(seconds=20),
    )

    payload = build_authorized_plan(
        plan_path=plan_path,
        repo_root=tmp_path,
        authorization_reference="user-approved-v4-batch",
        capacity_reference=None,
        capacity_fetcher=_capacity_fetcher(capacity_cache),
        capacity_lock_factory=lambda _accounts: nullcontext(),
        now=now,
    )

    capacity = payload["provider_capacity"]
    assert capacity["confirmed"] is True
    assert capacity["capacity_reference"].startswith("sha256:")
    assert capacity["evidence"] == {
        "schema_version": 2,
        "source": "anthropic-rate-limit-response-headers",
        "eligibility_policy": (
            "fresh-account-specific-utilization-below-100-percent"
        ),
        "confound_policy": (
            "accept-and-report-observed-nonzero-provider-utilization"
        ),
        "fetched_at": "2026-07-29T01:00:40+00:00",
        "max_age_seconds": 600,
        "accounts": {
            "agent": {
                "account": 3,
                "fetched_at": "2026-07-29T01:00:40+00:00",
                "five_hour_utilization_pct": 25.0,
                "five_hour_resets_at": "2026-07-29T06:00:00+00:00",
                "seven_day_utilization_pct": 48.0,
                "seven_day_resets_at": "2026-08-01T16:00:00+00:00",
            },
            "judge": {
                "account": 1,
                "fetched_at": "2026-07-29T01:00:40+00:00",
                "five_hour_utilization_pct": 7.0,
                "five_hour_resets_at": "2026-07-29T06:00:00+00:00",
                "seven_day_utilization_pct": 45.0,
                "seven_day_resets_at": "2026-07-30T02:00:00+00:00",
            },
        },
    }
    authorized_path = plan_path.with_name("dispatch_plan.authorized-v4.json")
    write_authorized_plan(authorized_path, payload)
    authorized = load_dispatch_plan(authorized_path, repo_root=tmp_path)
    assert authorized.v3_controls is not None
    commands = tuple(
        compile_run_command(slot, plan=authorized, repo_root=tmp_path)
        for slot in authorized.slots
    )
    assert authorized.v3_controls.authorized_batch_hash == authorization_batch_hash(
        authorized,
        commands,
        start_prefix=0,
        end_prefix=6,
    )


@pytest.mark.parametrize(
    ("agent_five_hour", "judge_five_hour"),
    ((100.0, 7.0), (25.0, 100.0)),
)
def test_v4_authorizer_rejects_exhausted_five_hour_usage(
    tmp_path: Path,
    agent_five_hour: float,
    judge_five_hour: float,
) -> None:
    now = datetime(2026, 7, 29, 1, 1, tzinfo=timezone.utc)
    plan_path, *_ = _write_fixture(tmp_path, study_id="rryas-headline-v4")
    capacity_cache = _write_capacity_cache(
        tmp_path / "usage_cache.json",
        fetched_at=now,
        agent_five_hour=agent_five_hour,
        judge_five_hour=judge_five_hour,
    )

    with pytest.raises(AuthorizationError, match="remaining provider capacity"):
        build_authorized_plan(
            plan_path=plan_path,
            repo_root=tmp_path,
            authorization_reference="user-approved-v4-batch",
            capacity_reference=None,
            capacity_fetcher=_capacity_fetcher(capacity_cache),
            capacity_lock_factory=lambda _accounts: nullcontext(),
            now=now,
        )


def test_v4_authorizer_rejects_stale_capacity_cache(tmp_path: Path) -> None:
    now = datetime(2026, 7, 29, 1, 20, tzinfo=timezone.utc)
    plan_path, *_ = _write_fixture(tmp_path, study_id="rryas-headline-v4")
    capacity_cache = _write_capacity_cache(
        tmp_path / "usage_cache.json",
        fetched_at=now - timedelta(seconds=601),
    )

    with pytest.raises(AuthorizationError, match="stale"):
        build_authorized_plan(
            plan_path=plan_path,
            repo_root=tmp_path,
            authorization_reference="user-approved-v4-batch",
            capacity_reference=None,
            capacity_fetcher=_capacity_fetcher(capacity_cache),
            capacity_lock_factory=lambda _accounts: nullcontext(),
            now=now,
        )


def test_v4_authorizer_rejects_stale_merged_account_observation(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 7, 29, 1, 20, tzinfo=timezone.utc)
    plan_path, *_ = _write_fixture(tmp_path, study_id="rryas-headline-v4")
    capacity_cache = _write_capacity_cache(
        tmp_path / "usage_cache.json",
        fetched_at=now,
        agent_fetched_at=now - timedelta(seconds=601),
    )

    with pytest.raises(AuthorizationError, match="stale"):
        build_authorized_plan(
            plan_path=plan_path,
            repo_root=tmp_path,
            authorization_reference="user-approved-v4-batch",
            capacity_reference=None,
            capacity_fetcher=_capacity_fetcher(capacity_cache),
            capacity_lock_factory=lambda _accounts: nullcontext(),
            now=now,
        )


def test_v4_authorizer_rejects_missing_account_telemetry(tmp_path: Path) -> None:
    now = datetime(2026, 7, 29, 1, 1, tzinfo=timezone.utc)
    plan_path, *_ = _write_fixture(tmp_path, study_id="rryas-headline-v4")
    capacity_cache = _write_capacity_cache(
        tmp_path / "usage_cache.json",
        fetched_at=now,
    )
    payload = json.loads(capacity_cache.read_text())
    payload["accounts"] = [
        account for account in payload["accounts"] if account["name"] != "account1"
    ]
    capacity_cache.write_text(json.dumps(payload))

    with pytest.raises(AuthorizationError, match="account1 usage windows"):
        build_authorized_plan(
            plan_path=plan_path,
            repo_root=tmp_path,
            authorization_reference="user-approved-v4-batch",
            capacity_reference=None,
            capacity_fetcher=_capacity_fetcher(capacity_cache),
            capacity_lock_factory=lambda _accounts: nullcontext(),
            now=now,
        )


def test_v4_authorizer_converts_account_lock_contention(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 7, 29, 1, 1, tzinfo=timezone.utc)
    plan_path, *_ = _write_fixture(tmp_path, study_id="rryas-headline-v4")
    capacity_cache = _write_capacity_cache(
        tmp_path / "usage_cache.json",
        fetched_at=now,
    )

    class ContendedLock:
        def __enter__(self):
            raise CapacityProbeError("account3 is already locked")

        def __exit__(self, *_args: object) -> None:
            return None

    with pytest.raises(AuthorizationError, match="account3 is already locked"):
        build_authorized_plan(
            plan_path=plan_path,
            repo_root=tmp_path,
            authorization_reference="user-approved-v4-batch",
            capacity_reference=None,
            capacity_fetcher=_capacity_fetcher(capacity_cache),
            capacity_lock_factory=lambda _accounts: ContendedLock(),
            now=now,
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


def test_v4_authorizer_cli_uses_fixed_live_account_probes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    now = datetime.now(timezone.utc)
    plan_path, *_ = _write_fixture(tmp_path, study_id="rryas-headline-v4")
    output = plan_path.with_name("dispatch_plan.authorized-v4.json")
    capacity_cache = _write_capacity_cache(
        tmp_path / "usage_cache.json",
        fetched_at=now,
    )
    fetcher = _capacity_fetcher(capacity_cache)
    calls: list[int] = []
    monkeypatch.setattr(authorize_headline_v3_batch, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        authorize_headline_v3_batch,
        "exclusive_provider_account_locks",
        lambda accounts: nullcontext(),
    )
    monkeypatch.setattr(
        authorize_headline_v3_batch,
        "fetch_provider_usage",
        lambda account: calls.append(account) or fetcher(account),
    )

    result = main(
        [
            "--plan",
            str(plan_path),
            "--output",
            str(output),
            "--authorization-reference",
            "user-approved-v4-batch",
        ]
    )

    assert result == 0
    assert calls == [3, 1]
    assert load_dispatch_plan(output, repo_root=tmp_path).paid_dispatch_authorized
    assert json.loads(capsys.readouterr().out)["authorized_end_prefix"] == 6


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
