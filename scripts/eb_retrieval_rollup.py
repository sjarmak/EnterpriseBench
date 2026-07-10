#!/usr/bin/env python3
"""Per-config retrieval rollup for the EnterpriseBench tool-access study.

Walks ``results/<run>/results.json`` files, joins each single-record run's
``agent_trace.jsonl`` with its task ground truth, and emits the mean retrieval
quality (``file_recall``, ``context_efficiency``, ``MRR``, plus recall/f1/ndcg
@k) per config — over **matched telemetry only** by default, so the arms are
compared on the tasks observed in every arm.

Usage:
    python scripts/eb_retrieval_rollup.py \
        --runs-dir results --benchmarks-dir benchmarks \
        --out results/retrieval_rollup.json

    # compare on all observed tasks (not just the matched intersection):
    python scripts/eb_retrieval_rollup.py --runs-dir results \
        --benchmarks-dir benchmarks --all
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

from eb_metrics.retrieval_rollup import (  # noqa: E402
    aggregate_retrieval,
    iter_run_retrievals,
)

logger = logging.getLogger("eb_retrieval_rollup")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs-dir", default="results",
                        help="Directory containing per-run subdirs (default: results).")
    parser.add_argument("--benchmarks-dir", default="benchmarks",
                        help="Task-definitions root, for ground_truth.json (default: benchmarks).")
    parser.add_argument("--pattern", default="**/results.json",
                        help="Glob (relative to --runs-dir) selecting results.json files.")
    parser.add_argument("--config-from", choices=("mode", "run_name"), default="mode",
                        help="Config bucket key: the run's mode (default) or its dir name.")
    parser.add_argument("--all", action="store_true",
                        help="Aggregate over all observed tasks, not just the matched intersection.")
    parser.add_argument("--out", default=None,
                        help="Write rollup JSON to this path (default: stdout).")
    parser.add_argument("--log-level", default="WARNING", help="Logging level (default: WARNING).")
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
    benchmarks_dir = Path(args.benchmarks_dir)
    if not benchmarks_dir.is_dir():
        print(f"error: benchmarks-dir not found: {benchmarks_dir}", file=sys.stderr)
        return 1

    dropped: dict[str, int] = {}
    runs = list(
        iter_run_retrievals(
            runs_dir,
            benchmarks_dir,
            pattern=args.pattern,
            config_from=args.config_from,
            dropped=dropped,
        )
    )
    payload = aggregate_retrieval(
        runs,
        matched_only=not args.all,
        config_key=args.config_from,
        dropped=dropped,
    )
    text = json.dumps(payload, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n")
        print(f"retrieval rollup written to {args.out} "
              f"({payload['matched_task_count']} matched tasks across "
              f"{len(payload['configs'])} configs)", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
