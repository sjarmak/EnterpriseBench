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

* **Validity** — an attempt whose persisted ``status`` says ``invalid`` or whose
  cache-isolation proof is absent/invalid is never selectable, whatever its
  ``scores`` block says. A reader that consults only ``scores`` resurrects
  invalid or cross-run-cache-confounded attempts.
* **Order** — among the valid, scored attempts, the *earliest* one represents
  the cell. Current runs use the host-authored ``results.json.started_at``;
  legacy runs lacking that field fall back to their trace timestamp and disclose
  that weaker provenance. An undated attempt sorts last.

Both ``analyze_scores`` (which reports the score) and ``cost_tracker`` (which
bills the cell) import from here. They must collapse a cell to the same attempt
or every score-vs-cost join pairs one run's score with another run's cost.

The trace fallback exists only for pre-clock historical results. New benchmark
runs are not allowed to make agent-controlled trace content their ordering key.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Lowercase as run_task._effective_status writes it; compared case-insensitively
# because the older verifier schema wrote it upper-case (EnterpriseBench-te9ah).
RUN_STATUS_INVALID = "invalid"

# Published in cost_report.json so a reader never has to infer the policy.
SELECTION_RULE = (
    "earliest valid attempt: ascending host-authored results.json.started_at "
    "timestamp, "
    "then run_dir. A result from the legacy corpus that lacks started_at falls "
    "back to agent_trace.jsonl and is explicitly labelled legacy_trace. The score "
    "is not an input — a re-run cell is not resolved in favour of its best "
    "outcome. Attempts persisted status=invalid, attempts without a valid "
    "zero-cross-run-read cache-isolation proof, and attempts the scoring layer "
    "produced no score for, are never selected. Matches analyze_scores."
)

ATTEMPT_TIMESTAMP_HOST = "results.started_at"
ATTEMPT_TIMESTAMP_LEGACY_TRACE = "legacy_trace"
ATTEMPT_TIMESTAMP_UNDATED = "undated"


# ---------------------------------------------------------------------------
# The pin: the study declares its selection before any outcome is read
# ---------------------------------------------------------------------------

# The only implemented selection. There is deliberately no "highest_score"
# value: the rule this bead removed must not be re-declarable from a config
# file, or the pin becomes a switch for turning the bias back on.
SELECTION_EARLIEST_VALID = "earliest_valid"

STUDY_SPEC_SCHEMA_VERSION = 1

# configs/study_spec.json, resolved from this file rather than from the working
# directory — the analysis scripts are run from batch jobs and from the repo
# root alike, and a cwd-relative spec would resolve to a different pin depending
# on where the caller stood.
DEFAULT_STUDY_SPEC = Path(__file__).resolve().parents[2] / "configs" / "study_spec.json"


class AttemptPolicyError(ValueError):
    """The declared policy cannot be honoured, so no analysis may proceed.

    Every path out of :func:`load_attempt_policy` and
    :meth:`AttemptPolicy.require_implemented` that is not a usable policy
    raises this. Falling back to the built-in rule on an unreadable or
    unrecognised spec would report a study under a rule the study did not
    declare — the failure the spec exists to make impossible.

    A ``ValueError`` subclass so that "the declared policy is unusable" is one
    catchable thing. Two channels — this for the loader, a bare ``ValueError``
    for the guard — meant no single ``except`` could wrap an entry point, which
    is the one place a friendly message for this failure belongs.
    """


@dataclass(frozen=True)
class AttemptTimestamp:
    """An attempt's ordering time and the provenance of that time."""

    value: str
    source: str


@dataclass(frozen=True)
class AttemptPolicy:
    """The attempt-selection rule a study declared, and where it declared it.

    Frozen because it is read once at an entry point and threaded down: a stage
    that could rewrite it mid-run would defeat "pinned before outcomes".
    """

    selection: str
    version: int
    spec_path: str

    def require_implemented(self, consumer: str) -> None:
        """Raise unless this code implements the declared selection.

        Both report producers call it before publishing the policy block, so no
        artifact can name a rule that is not the rule its rows were chosen by.
        It catches a policy constructed in code; :func:`load_attempt_policy`
        rejects the same values earlier.
        """

        if self.selection != SELECTION_EARLIEST_VALID:
            raise AttemptPolicyError(
                f"{consumer} implements {SELECTION_EARLIEST_VALID!r}, not "
                f"{self.selection!r}."
            )

    def as_dict(self) -> dict[str, Any]:
        """The published block. ``rule`` has one producer, so a reader comparing
        two artifacts is comparing the same sentence."""

        return {
            "selection": self.selection,
            "version": self.version,
            "spec_path": self.spec_path,
            "rule": SELECTION_RULE,
        }


def load_attempt_policy(spec_path: Path | None = None) -> AttemptPolicy:
    """Read the ``attempt_policy`` block of the StudySpec, or raise.

    Only this module's own key is read. ``configs/study_spec.json`` is shared
    with the wider Study Capsule (EnterpriseBench-rryas.11), which will add
    sibling blocks; rejecting a file for carrying keys this loader does not
    understand would force the two beads into a schema fight over one document.
    """

    path = DEFAULT_STUDY_SPEC if spec_path is None else Path(spec_path)

    if not path.is_file():
        raise AttemptPolicyError(
            f"StudySpec not found at {path}. The attempt-selection policy is "
            f"pinned in that file; analysis cannot declare a rule it has not read."
        )

    try:
        spec = json.loads(path.read_text())
    except ValueError as exc:
        raise AttemptPolicyError(f"StudySpec {path} is not valid JSON: {exc}") from exc
    except OSError as exc:
        raise AttemptPolicyError(f"StudySpec {path} cannot be read: {exc}") from exc

    if not isinstance(spec, dict):
        raise AttemptPolicyError(f"StudySpec {path} must be a JSON object.")

    declared_schema = spec.get("schema_version")
    # bool before equality: ``True == 1``, so a spec declaring
    # ``"schema_version": true`` would otherwise pass as version 1. The nested
    # ``version`` field already guards this; the two must agree.
    if (
        not isinstance(declared_schema, int)
        or isinstance(declared_schema, bool)
        or declared_schema != STUDY_SPEC_SCHEMA_VERSION
    ):
        raise AttemptPolicyError(
            f"StudySpec {path} declares schema_version={declared_schema!r}, "
            f"expected {STUDY_SPEC_SCHEMA_VERSION}. A spec written against "
            f"another schema may mean something different by the same key."
        )

    block = spec.get("attempt_policy")
    if not isinstance(block, dict):
        raise AttemptPolicyError(
            f"StudySpec {path} has no attempt_policy object. The selection rule "
            f"is not optional — an unpinned study cannot be reported."
        )

    selection = block.get("selection")
    if selection != SELECTION_EARLIEST_VALID:
        raise AttemptPolicyError(
            f"StudySpec {path} declares attempt_policy.selection={selection!r}, "
            f"which this code does not implement. The only implemented selection "
            f"is {SELECTION_EARLIEST_VALID!r}."
        )

    version = block.get("version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise AttemptPolicyError(
            f"StudySpec {path} declares attempt_policy.version={version!r}; "
            f"an integer is required so two artifacts can be compared by it."
        )

    return AttemptPolicy(selection=selection, version=version, spec_path=str(path))


def is_invalid_status(status: Any) -> bool:
    """True when a persisted run status marks the run unscoreable.

    Absent, null and empty all mean "not marked": a legacy run written before
    the field existed, and a current run that reached ``complete``, both land
    there. Only the explicit marker excludes, so this cannot silently drop a
    corpus that predates the field.
    """

    return isinstance(status, str) and status.strip().lower() == RUN_STATUS_INVALID


def cache_isolation_invalid_reason(result: Any) -> str | None:
    """Return why a result is cache-confounded, or ``None`` when proven isolated."""
    if not isinstance(result, dict):
        return "cache-isolation proof missing (legacy run)"
    tool_usage = result.get("tool_usage")
    proof = (
        tool_usage.get("cache_isolation")
        if isinstance(tool_usage, dict)
        else None
    )
    if not isinstance(proof, dict) or not proof:
        return "cache-isolation proof missing (legacy run)"
    if proof.get("valid") is not True:
        return str(proof.get("invalid_reason") or "cache-isolation proof is invalid")
    if proof.get("configured") is not True:
        return "cache-isolation mechanism was not configured"
    if not isinstance(proof.get("launcher_scope"), str) or not proof["launcher_scope"]:
        return "cache-isolation launcher scope is missing"
    if not isinstance(proof.get("mechanism"), str) or not proof["mechanism"]:
        return "cache-isolation mechanism is missing"
    if proof.get("cross_run_cache_read_tokens") != 0:
        return "cross-run cache reads were nonzero or unavailable"
    return None


def instant(stamp: str) -> tuple[int, float]:
    """Sortable instant for one ISO-8601 string.

    Parsed rather than compared as text. Raw string order only matches
    chronological order when every timestamp shares one exact format, and a
    study runs for months across CLI versions: ``...:00.123456Z`` sorts *before*
    ``...:00Z`` lexicographically because ``.`` < ``Z``, so a precision change
    mid-corpus would silently reorder cells with no adversary involved.

    The raw text is deliberately *not* carried in the key. Two spellings of one
    moment must compare equal, so that the tie falls through to ``run_dir`` —
    the documented tiebreak — rather than to whichever spelling happens to sort
    first. An unparseable string still has to sort somewhere, and it sorts after
    every parseable one, the same fail-late posture undated attempts get.
    """

    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return (1, 0.0)
    if parsed.tzinfo is None:
        # A naive stamp is read as UTC. Guessing local time would make the
        # order depend on the machine the report was generated on.
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (0, parsed.timestamp())


def newer_timestamp(entry: Any, current: str) -> str:
    """Fold one trace line's ISO-8601 ``timestamp`` into the running maximum.

    The single definition of "when did this attempt run". Both trace readers
    call it, so the two cannot drift into dating the same attempt differently
    and ordering a cell's attempts two ways. That guarantee is why a line which
    is valid JSON but not an object is absorbed here rather than at each call
    site: it carries no timestamp either way, and a caller that forgot the check
    would abort a whole scan on one junk line while the other reader skipped it.

    ``""`` means "no timestamp seen yet" and loses to anything, which is why it
    is special-cased rather than run through :func:`instant`. A stamp that ties
    the running maximum leaves it alone, so a trace whose stamps are all
    unparseable is dated by its first line rather than by text order.
    """

    if not isinstance(entry, dict):
        return current
    stamp = entry.get("timestamp")
    if not isinstance(stamp, str) or not stamp:
        return current
    if not current:
        return stamp
    return stamp if instant(stamp) > instant(current) else current


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
                last = newer_timestamp(entry, last)
    except OSError as exc:
        logger.warning("Cannot date attempt %s: %s", attempt_dir, exc)
        return ""
    return last


def read_attempt_timestamp(attempt_dir: Path) -> AttemptTimestamp:
    """Read the host attempt clock, falling back only for a legacy result.

    Presence of ``started_at`` marks a current result. If that field is invalid,
    the attempt is undated; an agent-controlled trace must not replace a corrupt
    host clock. Only a result that genuinely predates the field may use the
    disclosed legacy trace fallback.
    """

    results_path = attempt_dir / "results.json"
    if results_path.is_file():
        try:
            payload = json.loads(results_path.read_text())
        except (OSError, ValueError, RecursionError):
            return AttemptTimestamp("", ATTEMPT_TIMESTAMP_UNDATED)

        if not isinstance(payload, dict):
            return AttemptTimestamp("", ATTEMPT_TIMESTAMP_UNDATED)

        if "started_at" in payload:
            started_at = payload.get("started_at")
            if isinstance(started_at, str) and instant(started_at)[0] == 0:
                return AttemptTimestamp(started_at, ATTEMPT_TIMESTAMP_HOST)
            return AttemptTimestamp("", ATTEMPT_TIMESTAMP_UNDATED)

    trace_timestamp = read_trace_timestamp(attempt_dir)
    if trace_timestamp and instant(trace_timestamp)[0] == 0:
        return AttemptTimestamp(
            trace_timestamp,
            ATTEMPT_TIMESTAMP_LEGACY_TRACE,
        )
    return AttemptTimestamp("", ATTEMPT_TIMESTAMP_UNDATED)


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


def attempt_sort_key(
    trace_timestamp: str, run_dir: str
) -> tuple[int, tuple[int, float], str]:
    """Total order over a cell's attempts; ``min`` of it is the selected one.

    The leading flag sorts attempts this module cannot date last rather than
    first, which is where empty-string-ascending would otherwise put them.
    Undateable is one class, not two: an absent stamp and an unparseable one are
    equally uninformative about when the attempt ran, so the flag is taken from
    :func:`instant` rather than from emptiness. Ranking a corrupt stamp ahead of
    a missing one would make writing garbage into the trace a cheaper way to win
    selection than writing a plausible early date (EnterpriseBench-rryas.23).

    Both remaining components are content-derived, so the selection does not
    depend on scan order or filesystem order.
    """

    moment = instant(trace_timestamp)
    return (moment[0], moment, run_dir)
