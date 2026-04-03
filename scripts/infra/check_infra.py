#!/usr/bin/env python3
"""Pre-run infrastructure readiness checker for EnterpriseBench.

Validates OAuth tokens, Docker, and disk space before launching runs.
Can auto-refresh expired tokens via refresh_token grant.

Usage:
    python3 scripts/infra/check_infra.py
    python3 scripts/infra/check_infra.py --refresh-tokens
    python3 scripts/infra/check_infra.py --format json

Exit code 0 = ready, 1 = blocked.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from account_health import collect_account_status, discover_account_homes

REAL_HOME = os.environ.get("HOME", os.path.expanduser("~"))


def try_refresh_token(creds_file: Path) -> dict | None:
    """Attempt to refresh an expired OAuth token. Returns new expiry info or None."""
    try:
        data = json.loads(creds_file.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    oauth = data.get("claudeAiOauth", {})
    refresh_token = oauth.get("refreshToken")
    if not refresh_token:
        return None

    import urllib.request
    import urllib.error

    payload = json.dumps({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
    }).encode()

    req = urllib.request.Request(
        "https://console.anthropic.com/api/oauth/token",
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "eb-check-infra/1.0"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            token_data = json.loads(resp.read())
    except (urllib.error.HTTPError, urllib.error.URLError, OSError):
        return None

    new_access = token_data.get("access_token")
    if not new_access:
        return None

    expires_in = token_data.get("expires_in", 28800)
    oauth["accessToken"] = new_access
    new_refresh = token_data.get("refresh_token")
    if new_refresh:
        oauth["refreshToken"] = new_refresh
    oauth["expiresAt"] = int(time.time() * 1000) + (expires_in * 1000)
    data["claudeAiOauth"] = oauth

    try:
        creds_file.write_text(json.dumps(data, indent=2))
    except OSError:
        pass

    return {"expires_in": expires_in, "remaining_min": expires_in // 60}


def check_oauth_token(home_dir: str | None = None, allow_refresh: bool = False) -> dict:
    """Check OAuth token validity and time remaining."""
    home = home_dir or REAL_HOME
    creds_file = Path(home) / ".claude" / ".credentials.json"

    if not creds_file.is_file():
        return {
            "check": "oauth_token",
            "status": "FAIL",
            "message": f"No credentials file at {creds_file}",
            "home": home,
        }

    try:
        data = json.loads(creds_file.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return {
            "check": "oauth_token",
            "status": "FAIL",
            "message": f"Cannot read credentials: {e}",
            "home": home,
        }

    oauth = data.get("claudeAiOauth", {})
    expires_at_ms = oauth.get("expiresAt", 0)
    now_ms = int(time.time() * 1000)
    remaining_s = (expires_at_ms - now_ms) / 1000
    remaining_min = int(remaining_s / 60)

    has_refresh = bool(oauth.get("refreshToken"))

    if remaining_s <= 0:
        if has_refresh and allow_refresh:
            refresh_result = try_refresh_token(creds_file)
            if refresh_result:
                return {
                    "check": "oauth_token",
                    "status": "OK",
                    "message": f"Token was expired, refreshed successfully ({refresh_result['remaining_min']} min remaining)",
                    "remaining_minutes": refresh_result["remaining_min"],
                    "has_refresh_token": True,
                    "home": home,
                }
            else:
                return {
                    "check": "oauth_token",
                    "status": "FAIL",
                    "message": f"Access token expired ({abs(remaining_min)} min ago). Refresh failed. Run: python3 scripts/infra/headless_login.py --account N",
                    "remaining_minutes": remaining_min,
                    "has_refresh_token": has_refresh,
                    "home": home,
                }
        status = "WARN" if has_refresh else "FAIL"
        action = "refresh/login recommended" if has_refresh else "Run: claude login"
        return {
            "check": "oauth_token",
            "status": status,
            "message": f"Token EXPIRED ({abs(remaining_min)} min ago), {action}",
            "remaining_minutes": remaining_min,
            "has_refresh_token": has_refresh,
            "home": home,
        }
    elif remaining_s < 1800:  # < 30 min
        return {
            "check": "oauth_token",
            "status": "WARN",
            "message": f"Token expires in {remaining_min} min (< 30 min margin). Refresh recommended.",
            "remaining_minutes": remaining_min,
            "has_refresh_token": has_refresh,
            "home": home,
        }
    else:
        return {
            "check": "oauth_token",
            "status": "OK",
            "message": f"Token valid ({remaining_min} min remaining)",
            "remaining_minutes": remaining_min,
            "has_refresh_token": has_refresh,
            "home": home,
        }


def check_multi_account_tokens(allow_refresh: bool = False) -> list[dict]:
    """Check tokens for all accounts under ~/.claude-homes/."""
    real_home_path = Path(REAL_HOME)
    return [
        check_oauth_token(
            None if home == real_home_path else str(home),
            allow_refresh=allow_refresh,
        )
        for home in discover_account_homes(real_home_path)
    ]


def check_account_readiness() -> dict:
    """Summarize launch-safe accounts using deterministic local signals."""
    report = collect_account_status()
    summary = report["summary"]
    action = report["recommended_action"]
    status = "OK" if report["ok_to_launch"] else "FAIL"
    return {
        "check": "account_readiness",
        "status": status,
        "message": f"{summary}; action={action}",
    }


def check_docker() -> dict:
    """Check Docker daemon is running."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True, timeout=10,
        )
        if result.returncode == 0:
            return {"check": "docker", "status": "OK", "message": "Docker daemon is running"}
        else:
            stderr = result.stderr.decode(errors="replace")[:200]
            return {"check": "docker", "status": "FAIL", "message": f"Docker not responding: {stderr}"}
    except FileNotFoundError:
        return {"check": "docker", "status": "FAIL", "message": "Docker not installed"}
    except subprocess.TimeoutExpired:
        return {"check": "docker", "status": "FAIL", "message": "Docker info timed out"}


def check_disk_space() -> dict:
    """Check available disk space."""
    usage = shutil.disk_usage(REAL_HOME)
    free_gb = usage.free / (1024 ** 3)
    total_gb = usage.total / (1024 ** 3)
    pct_free = (usage.free / usage.total) * 100

    if free_gb < 5:
        return {
            "check": "disk_space",
            "status": "FAIL",
            "message": f"Only {free_gb:.1f}GB free of {total_gb:.0f}GB ({pct_free:.0f}% free)",
        }
    elif free_gb < 20:
        return {
            "check": "disk_space",
            "status": "WARN",
            "message": f"{free_gb:.1f}GB free of {total_gb:.0f}GB ({pct_free:.0f}% free). May run low.",
        }
    else:
        return {
            "check": "disk_space",
            "status": "OK",
            "message": f"{free_gb:.1f}GB free of {total_gb:.0f}GB ({pct_free:.0f}% free)",
        }


def format_table(results: list[dict]) -> str:
    """Format results as colored table."""
    lines = ["Infrastructure Readiness Check", "=" * 60]
    status_colors = {"OK": "\033[92m", "WARN": "\033[93m", "FAIL": "\033[91m"}
    reset = "\033[0m"
    fails = warns = 0

    for r in results:
        status = r["status"]
        color = status_colors.get(status, "")
        home_suffix = f" [{r['home']}]" if "home" in r else ""
        lines.append(f"  {color}[{status:4s}]{reset}  {r['check']:25s}  {r['message']}{home_suffix}")
        if status == "FAIL":
            fails += 1
        elif status == "WARN":
            warns += 1

    lines.append("")
    if fails:
        lines.append(f"\033[91mBLOCKED: {fails} critical issue(s) must be fixed before running.\033[0m")
    elif warns:
        lines.append(f"\033[93mREADY with {warns} warning(s). Runs may partially fail.\033[0m")
    else:
        lines.append("\033[92mALL CLEAR: Infrastructure ready for benchmark runs.\033[0m")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Check infrastructure readiness before benchmark runs.")
    parser.add_argument("--format", choices=["table", "json"], default="table")
    parser.add_argument("--refresh-tokens", action="store_true", help="Auto-refresh expired OAuth tokens.")
    args = parser.parse_args()

    results = []
    results.extend(check_multi_account_tokens(allow_refresh=args.refresh_tokens))
    results.append(check_account_readiness())
    results.append(check_docker())
    results.append(check_disk_space())

    if args.format == "json":
        output = {
            "checks": results,
            "ok": sum(1 for r in results if r["status"] == "OK"),
            "warn": sum(1 for r in results if r["status"] == "WARN"),
            "fail": sum(1 for r in results if r["status"] == "FAIL"),
        }
        print(json.dumps(output, indent=2))
    else:
        print(format_table(results))

    if any(r["status"] == "FAIL" for r in results):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
