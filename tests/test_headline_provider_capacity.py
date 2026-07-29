from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for import_path in (
    PROJECT_ROOT / "scripts" / "infra",
    PROJECT_ROOT / "scripts" / "orchestration",
):
    sys.path.insert(0, str(import_path))

import headline_provider_capacity  # noqa: E402
from headline_provider_capacity import (  # noqa: E402
    CapacityProbeError,
    build_live_capacity_evidence,
    exclusive_provider_account_locks,
    fetch_provider_usage,
)


def _usage(fetched_at: datetime) -> dict[str, object]:
    return {
        "fetched_at": fetched_at.isoformat(),
        "five_hour": {
            "utilization": 0.0,
            "resets_at": "2026-07-29T06:00:00+00:00",
        },
        "seven_day": {
            "utilization": 48.0,
            "resets_at": "2026-08-01T16:00:00+00:00",
        },
        "email": "must-not-be-retained@example.com",
        "access_token": "must-not-be-retained",
    }


def test_live_evidence_fetches_exact_accounts_and_redacts_source() -> None:
    observed_at = datetime(2026, 7, 29, 1, 0, tzinfo=timezone.utc)
    calls: list[int] = []

    def fetcher(account_number: int) -> dict[str, object]:
        calls.append(account_number)
        return _usage(observed_at)

    evidence = build_live_capacity_evidence(
        agent_account=3,
        judge_account=1,
        fetcher=fetcher,
    )

    assert calls == [3, 1]
    assert evidence["accounts"]["agent"]["account"] == 3
    assert evidence["accounts"]["judge"]["account"] == 1
    assert evidence["schema_version"] == 2
    assert (
        evidence["eligibility_policy"]
        == "fresh-account-specific-utilization-below-100-percent"
    )
    assert (
        evidence["confound_policy"]
        == "accept-and-report-observed-nonzero-provider-utilization"
    )
    serialized = str(evidence)
    assert "must-not-be-retained" not in serialized
    assert "email" not in serialized
    assert "access_token" not in serialized


def test_production_fetch_uses_fixed_claude_home_account(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    homes = tmp_path / "claude-homes"
    expected = homes / "account3"
    observed_paths: list[Path] = []
    monkeypatch.setattr(headline_provider_capacity, "CLAUDE_HOMES", homes)

    def load_token(account_dir: Path) -> str:
        observed_paths.append(account_dir)
        return "test-token"

    monkeypatch.setattr(headline_provider_capacity, "load_token", load_token)
    monkeypatch.setattr(
        headline_provider_capacity,
        "fetch_usage_for_token",
        lambda token: {
            "five_hour": {
                "utilization": 0.0,
                "resets_at": "2026-07-29T06:00:00+00:00",
            },
            "seven_day": {
                "utilization": 48.0,
                "resets_at": "2026-08-01T16:00:00+00:00",
            },
        },
    )

    result = fetch_provider_usage(3)

    assert observed_paths == [expected]
    assert result["five_hour"]["utilization"] == 0.0
    assert "fetched_at" in result


def test_provider_account_locks_reject_overlapping_consumer(
    tmp_path: Path,
) -> None:
    with exclusive_provider_account_locks({1, 3}, lock_dir=tmp_path):
        with pytest.raises(CapacityProbeError, match="account3"):
            with exclusive_provider_account_locks({3}, lock_dir=tmp_path):
                pytest.fail("overlapping account lock must not be acquired")


def test_provider_account_lock_files_are_private(tmp_path: Path) -> None:
    with exclusive_provider_account_locks({1}, lock_dir=tmp_path):
        lock_path = tmp_path / "account1.lock"
        assert lock_path.stat().st_mode & 0o777 == 0o600
        assert tmp_path.stat().st_mode & 0o777 == 0o700
