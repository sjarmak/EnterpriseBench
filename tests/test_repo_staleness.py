"""Tests for scripts/infra/check_repo_staleness.py."""

import json
import subprocess
import sys
from datetime import date, timedelta

import pytest

sys.path.insert(
    0,
    str(
        __import__("pathlib").Path(__file__).resolve().parents[1] / "scripts" / "infra"
    ),
)
from check_repo_staleness import check_staleness, load_manifest


def _make_entries(dates: list[str]) -> list[dict]:
    return [
        {
            "url": f"https://github.com/org/repo-{i}",
            "pinned_rev": f"v{i}.0",
            "last_verified": d,
        }
        for i, d in enumerate(dates)
    ]


class TestCheckStaleness:
    def test_all_fresh(self) -> None:
        today = date(2026, 4, 2)
        entries = _make_entries(["2026-01-01", "2026-03-15"])
        stale = check_staleness(entries, today=today)
        assert stale == []

    def test_stale_detected(self) -> None:
        today = date(2026, 10, 5)
        entries = _make_entries(["2026-01-01", "2026-10-01"])
        stale = check_staleness(entries, today=today)
        assert len(stale) == 1
        assert stale[0]["url"] == "https://github.com/org/repo-0"
        assert stale[0]["days_since_verified"] == 277

    def test_exactly_at_threshold_is_stale(self) -> None:
        today = date(2026, 4, 2)
        boundary_date = (today - timedelta(days=183)).isoformat()
        entries = _make_entries([boundary_date])
        stale = check_staleness(entries, today=today)
        assert len(stale) == 1

    def test_one_day_before_threshold_is_fresh(self) -> None:
        today = date(2026, 4, 2)
        fresh_date = (today - timedelta(days=182)).isoformat()
        entries = _make_entries([fresh_date])
        stale = check_staleness(entries, today=today)
        assert stale == []

    def test_stale_sorted_by_days_descending(self) -> None:
        today = date(2026, 12, 1)
        entries = _make_entries(["2026-01-15", "2025-06-01", "2026-03-01"])
        stale = check_staleness(entries, today=today)
        assert len(stale) == 3
        days = [e["days_since_verified"] for e in stale]
        assert days == sorted(days, reverse=True)

    def test_custom_threshold(self) -> None:
        today = date(2026, 4, 2)
        entries = _make_entries(["2026-03-01"])
        stale = check_staleness(entries, today=today, threshold_days=30)
        assert len(stale) == 1

    def test_empty_entries(self) -> None:
        stale = check_staleness([], today=date(2026, 4, 2))
        assert stale == []


class TestLoadManifest:
    def test_load_from_file(self, tmp_path: __import__("pathlib").Path) -> None:
        data = [
            {
                "url": "https://github.com/a/b",
                "pinned_rev": "v1",
                "last_verified": "2026-04-02",
            }
        ]
        manifest = tmp_path / "repo_versions.json"
        manifest.write_text(json.dumps(data))
        loaded = load_manifest(manifest)
        assert loaded == data


class TestCLI:
    def test_json_flag(self, tmp_path: __import__("pathlib").Path) -> None:
        data = [
            {
                "url": "https://github.com/a/b",
                "pinned_rev": "v1",
                "last_verified": "2020-01-01",
            },
        ]
        manifest = tmp_path / "repo_versions.json"
        manifest.write_text(json.dumps(data))

        result = subprocess.run(
            [
                sys.executable,
                "scripts/infra/check_repo_staleness.py",
                "--json",
                "--manifest",
                str(manifest),
            ],
            capture_output=True,
            text=True,
            cwd=str(__import__("pathlib").Path(__file__).resolve().parents[1]),
        )
        output = json.loads(result.stdout)
        assert output["stale_count"] == 1
        assert output["total_count"] == 1
        assert len(output["stale"]) == 1
        assert result.returncode == 1

    def test_no_stale_exit_zero(self, tmp_path: __import__("pathlib").Path) -> None:
        today = date.today().isoformat()
        data = [
            {
                "url": "https://github.com/a/b",
                "pinned_rev": "v1",
                "last_verified": today,
            }
        ]
        manifest = tmp_path / "repo_versions.json"
        manifest.write_text(json.dumps(data))

        result = subprocess.run(
            [
                sys.executable,
                "scripts/infra/check_repo_staleness.py",
                "--manifest",
                str(manifest),
            ],
            capture_output=True,
            text=True,
            cwd=str(__import__("pathlib").Path(__file__).resolve().parents[1]),
        )
        assert result.returncode == 0
        assert "up to date" in result.stdout
