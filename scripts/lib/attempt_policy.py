"""Which attempt of a (task_id, mode) cell the analysis is allowed to use.

The rule is *prespecified*: it is fixed before any score is read, and no field
of the outcome enters it. That is the whole point. Selecting the highest-scoring
attempt of a re-run cell takes a maximum over N draws, so a cell's reported
score rises with the number of times it happened to be retried — and arms are
not retried equally, so the bias is not even a constant offset between arms.
The re-run channel exists to replace attempts that were *invalid* (infra error,
expired credential, broken MCP pre-flight), not to resample a score that was
already valid.

Two independent gates, both fail-closed:

* **Validity** — an attempt whose persisted ``status`` says ``invalid`` is never
  selectable, whatever its ``scores`` block says. run_task writes that status
  for every run that failed short of ``complete``, including runs that reached
  the verifier and were scored before the integrity or zero-MCP gate fired. A
  reader that consults only ``scores`` resurrects exactly those runs.
* **Order** — among the valid, scored attempts, the *earliest* one represents
  the cell. Ascending trace timestamp, then run directory; an attempt with no
  timestamp at all sorts last, so a trace that could not be dated can never
  displace one that could.

Both ``analyze_scores`` (which reports the score) and ``cost_tracker`` (which
bills the cell) import from here. They must collapse a cell to the same attempt
or every score-vs-cost join pairs one run's score with another run's cost.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Lowercase as run_task._effective_status writes it; compared case-insensitively
# because the older verifier schema wrote it upper-case (EnterpriseBench-te9ah).
RUN_STATUS_INVALID = "invalid"

# Published in cost_report.json so a reader never has to infer the policy.
SELECTION_RULE = (
    "earliest valid attempt: ascending trace timestamp, then run_dir. The score "
    "is not an input — a re-run cell is not resolved in favour of its best "
    "outcome. Attempts persisted status=invalid, and attempts the scoring layer "
    "produced no score for, are never selected. Matches analyze_scores."
)


def is_invalid_status(status: Any) -> bool:
    """True when a persisted run status marks the run unscoreable.

    Absent, null and empty all mean "not marked": a legacy run written before
    the field existed, and a current run that reached ``complete``, both land
    there. Only the explicit marker excludes, so this cannot silently drop a
    corpus that predates the field.
    """

    return isinstance(status, str) and status.strip().lower() == RUN_STATUS_INVALID


def newer_timestamp(entry: dict[str, Any], current: str) -> str:
    """Fold one trace line's ISO-8601 ``timestamp`` into the running maximum.

    The single definition of "when did this attempt run". Both trace readers
    call it, so the two cannot drift into dating the same attempt differently
    and ordering a cell's attempts two ways.
    """

    stamp = entry.get("timestamp")
    if isinstance(stamp, str) and stamp > current:
        return stamp
    return current


def read_trace_timestamp(attempt_dir: Path) -> str:
    """Date an attempt from its ``agent_trace.jsonl``, or "" if it cannot be.

    File mtime is deliberately not consulted: it survives neither a clone nor a
    rescore pass, and the ordering it would produce depends on which machine
    the report was generated on.
    """

    trace_path = attempt_dir / "agent_trace.jsonl"
    if not trace_path.is_file():
        return ""

    last = ""
    try:
        with trace_path.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except (ValueError, RecursionError):
                    continue
                if isinstance(entry, dict):
                    last = newer_timestamp(entry, last)
    except OSError as exc:
        logger.warning("Cannot date attempt %s: %s", attempt_dir, exc)
        return ""
    return last


def run_dir_label(attempt_dir: Path, root: Path) -> str:
    """Identify an attempt's directory, relative to *root* when it is under it.

    Both a published field of cost_report.json and the last tiebreak component
    of :func:`attempt_sort_key`, which is why the two modules share one
    definition: an absolute path would commit one machine's home directory and
    make the report non-portable, and two modules labelling the same directory
    differently would break the tie two ways. Falls back to the absolute path
    for a directory outside *root* — still correct, just not portable.
    """

    try:
        return str(attempt_dir.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(attempt_dir)


def attempt_sort_key(trace_timestamp: str, run_dir: str) -> tuple[int, str, str]:
    """Total order over a cell's attempts; ``min`` of it is the selected one.

    The leading flag sorts undated attempts last rather than first, which is
    where empty-string-ascending would otherwise put them. Both remaining
    components are content-derived, so the selection does not depend on scan
    order or filesystem order.
    """

    return (0 if trace_timestamp else 1, trace_timestamp, run_dir)
