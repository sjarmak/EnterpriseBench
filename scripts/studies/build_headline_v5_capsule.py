#!/usr/bin/env python3
"""Build the no-spend v5 successor after v4 failed before agent inference."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
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


def write_capsule(repo_root: Path, build, *, check: bool) -> None:
    """Write or verify the v5 capsule."""

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
