from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "infra"))

import fetch_usage  # noqa: E402


def test_usage_cache_and_directory_are_private(
    tmp_path: Path,
    monkeypatch,
) -> None:
    cache = tmp_path / "claude-usage" / "usage_cache.json"
    monkeypatch.setattr(fetch_usage, "USAGE_CACHE", cache)

    fetch_usage.update_cache(
        [{"name": "account1", "email": "private@example.com"}]
    )

    assert cache.parent.stat().st_mode & 0o777 == 0o700
    assert cache.stat().st_mode & 0o777 == 0o600
