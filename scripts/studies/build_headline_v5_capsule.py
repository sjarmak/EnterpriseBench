#!/usr/bin/env python3
"""Build the no-spend v5 successor after v4 failed before agent inference."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
for import_path in (
    REPO_ROOT / "lib",
    REPO_ROOT / "scripts" / "infra",
    REPO_ROOT / "scripts" / "orchestration",
    REPO_ROOT / "scripts" / "studies",
):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from build_headline_v4_capsule import (  # noqa: E402
    _git_revision,
    build_core_payloads as _build_core_payloads,
    configured_revision as _configured_revision,
    write_capsule as _write_capsule,
)
from eb_study import StudySpec  # noqa: E402
from headline_protocol import V5_PROTOCOL  # noqa: E402

V5_CONFIG_DIR = Path("configs/studies") / V5_PROTOCOL.study_id
V5_TERMINAL = (
    Path("results/studies") / V5_PROTOCOL.study_id / "batch-001-terminal.json"
)
V5_FROZEN_CONFIG_COMMIT = "51b8127"
V5_PURPOSE = (
    "Confirmatory Claude Sonnet 5 protocol comparison on the unchanged "
    "31-task v4 population after v4 failed during run_task module import "
    "before agent startup; the isolated no-tool judge and every experimental "
    "treatment remain unchanged."
)


def build_core_payloads(repo_root: Path, *, revision: str):
    """Derive every v5 artifact without writing or launching a model."""

    return _build_core_payloads(
        repo_root,
        revision=revision,
        protocol=V5_PROTOCOL,
        config_dir=V5_CONFIG_DIR,
        purpose=V5_PURPOSE,
    )


def _committed_capsule_bytes(repo_root: Path, name: str) -> bytes:
    result = subprocess.run(
        [
            "git",
            "show",
            f"{V5_FROZEN_CONFIG_COMMIT}:{V5_CONFIG_DIR / name}",
        ],
        cwd=repo_root,
        capture_output=True,
        check=True,
    )
    return result.stdout


def write_capsule(repo_root: Path, build, *, check: bool) -> None:
    """Write or verify the v5 capsule."""

    if (repo_root.resolve() / V5_TERMINAL).is_file():
        if not check:
            raise ValueError("terminal v5 capsule cannot be rewritten")
        required = {
            "analysis_plan.json",
            "dispatch_plan.json",
            "final_manifest.json",
            "preflight_evidence.json",
            "study_spec.json",
        }
        output_dir = repo_root.resolve() / V5_CONFIG_DIR
        for name in sorted(required):
            path = output_dir / name
            if (
                not path.is_file()
                or path.read_bytes()
                != _committed_capsule_bytes(repo_root, name)
            ):
                raise ValueError(
                    f"terminal v5 capsule artifact drifted: {path}"
                )
        return
    _write_capsule(
        repo_root,
        build,
        check=check,
        config_dir=V5_CONFIG_DIR,
    )


def configured_revision(repo_root: Path) -> str:
    """Return the full revision bound by the frozen v5 StudySpec."""

    return _configured_revision(repo_root, config_dir=V5_CONFIG_DIR)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if committed v5 artifacts differ; do not write files.",
    )
    args = parser.parse_args(argv)
    revision = (
        configured_revision(REPO_ROOT) if args.check else _git_revision(REPO_ROOT)
    )
    build = build_core_payloads(REPO_ROOT, revision=revision)
    write_capsule(REPO_ROOT, build, check=args.check)
    print(
        json.dumps(
            {
                "study_id": V5_PROTOCOL.study_id,
                "tasks": len(build.manifest["tasks"]),
                "slots": len(
                    build.manifest["execution_configuration"]["execution_order"]
                ),
                "harness_hash": build.manifest["harness_hash"],
                "spec_hash": StudySpec.from_json(build.spec).spec_hash,
                "paid_dispatch_authorized": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
