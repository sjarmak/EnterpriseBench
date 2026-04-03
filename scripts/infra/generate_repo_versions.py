#!/usr/bin/env python3
"""Scan all task.toml files and generate configs/repo_versions.json."""

import json
import pathlib
from datetime import date, timezone

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

ROOT = pathlib.Path(__file__).resolve().parents[2]
BENCHMARKS_DIR = ROOT / "benchmarks"
OUTPUT_PATH = ROOT / "configs" / "repo_versions.json"


def scan_task_tomls() -> dict[tuple[str, str], dict]:
    """Parse all task.toml files and collect unique (url, rev) pairs."""
    repos: dict[tuple[str, str], dict] = {}

    for toml_path in sorted(BENCHMARKS_DIR.rglob("task.toml")):
        # Skip archived tasks
        if "_archived" in toml_path.parts:
            continue

        with open(toml_path, "rb") as f:
            data = tomllib.load(f)

        for repo in data.get("repos", []):
            url = repo.get("url", "")
            rev = repo.get("rev", "")
            if url and rev:
                key = (url, rev)
                if key not in repos:
                    repos[key] = {
                        "url": url,
                        "pinned_rev": rev,
                        "last_verified": date.today().isoformat(),
                    }

    return repos


def generate_manifest() -> list[dict]:
    """Generate the repo versions manifest."""
    repos = scan_task_tomls()
    # Sort by URL then rev for stable output
    entries = sorted(repos.values(), key=lambda e: (e["url"], e["pinned_rev"]))
    return entries


def main() -> None:
    entries = generate_manifest()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(entries, f, indent=2)
        f.write("\n")
    print(f"Generated {OUTPUT_PATH} with {len(entries)} repo entries")


if __name__ == "__main__":
    main()
