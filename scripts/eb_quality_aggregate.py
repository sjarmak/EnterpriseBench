#!/usr/bin/env python3
"""Standalone CLI: build the codeprobe quality_metrics block for EB runs.

Walks ``results/<run>/results.json`` files under ``--runs-dir``, projects
each record through the EB → codeprobe trace-quality adapter, and
writes the resulting ``quality_metrics`` dict to ``--out`` (or stdout).

Schema is codeprobe's shared ``TraceQualityReporter.to_dict()`` shape
(schema_version 1) — see ``docs/trace_quality.md`` in the codeprobe
repo for the full contract.

Usage:
    python scripts/eb_quality_aggregate.py --runs-dir results --out results/quality_metrics.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LIB_DIR = PROJECT_ROOT / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from eb_metrics.aggregate_quality import build_quality_metrics  # noqa: E402

logger = logging.getLogger("eb_quality_aggregate")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--runs-dir",
        default="results",
        help="Directory containing per-run subdirs (default: results).",
    )
    parser.add_argument(
        "--pattern",
        default="*/results.json",
        help="Glob (relative to --runs-dir) selecting results.json files.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Write quality_metrics JSON to this path (default: stdout).",
    )
    parser.add_argument(
        "--benchmarks-dir",
        default=None,
        help=(
            "Task-definitions root (e.g. benchmarks/). When set, retrieval "
            "recall/f1 is computed by joining each single-record run dir's "
            "agent_trace.jsonl with its task ground_truth.json."
        ),
    )
    parser.add_argument(
        "--experiment-warning",
        action="append",
        default=[],
        help="Add an experiment-level warning kind (repeatable).",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        help="Logging level for adapter warnings (default: WARNING).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.WARNING),
        format="%(levelname)s %(name)s: %(message)s",
    )

    runs_dir = Path(args.runs_dir)
    if not runs_dir.is_dir():
        print(f"error: runs-dir not found: {runs_dir}", file=sys.stderr)
        return 1

    benchmarks_dir = Path(args.benchmarks_dir) if args.benchmarks_dir else None
    if benchmarks_dir is not None and not benchmarks_dir.is_dir():
        print(f"error: benchmarks-dir not found: {benchmarks_dir}", file=sys.stderr)
        return 1

    payload = build_quality_metrics(
        runs_dir,
        pattern=args.pattern,
        experiment_warnings=args.experiment_warning,
        benchmarks_dir=benchmarks_dir,
    )
    text = json.dumps(payload, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n")
        print(f"quality_metrics written to {args.out}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
