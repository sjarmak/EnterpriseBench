#!/usr/bin/env python3
"""Audit agent traces for source that escaped the run's authorized mirror set.

EnterpriseBench pins every task to a specific revision of each repo, mirrored on
Sourcegraph as `sg-evals/<project>--<shortsha>`. The pin is the guarantee that
every arm of a comparison sees the same source.

Sourcegraph's precise (SCIP) code-intel links references across repos by package
moniker. When several revisions of the same project are present on the instance,
`find_references` on an *exported* symbol resolves into sibling mirrors and into
upstream HEAD. The `repo` argument is a seed position, not a filter, so those
results cannot be scoped away client-side. An agent that follows such a
reference with `read_file` pulls wrong-revision source into its context.

Only the MCP arms can do this: the baseline arm has /workspace at the pinned
revision and no cross-repo index to traverse.

Two escape modes, deliberately kept apart because their severity differs:

  PIN_VIOLATING  A different revision of the SAME project (sibling mirror, or
                 upstream HEAD). Breaks the revision pin. The acute mode.
  FOREIGN        An unrelated project. Global-index bleed: noisy, and it widens
                 the context, but it does not violate the revision pin.

Usage:
    python scripts/analysis/audit_mirror_contamination.py --runs-dir results/runs
    python scripts/analysis/audit_mirror_contamination.py --runs-dir results/runs --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

AUTHORIZED = "authorized"
PIN_VIOLATING = "pin_violating"
FOREIGN = "foreign"

MIRROR_PREFIX = "sg-evals/"

# Runs withdrawn from analysis. Auditing them would report contamination for
# runs nobody scores.
INVALIDATED_DIR = "_invalidated"

# `rep1`, `rep2`, ... — a replicate of a mode, never a mode itself.
_REPLICATE_DIR = re.compile(r"rep\d+")

# `MCP filter: `repo:^github.com/sg-evals/react--ab18f33d$``
_MIRROR_RE = re.compile(r"repo:\^github\.com/(sg-evals/[\w.\-]+)\$")
# `Upstream: `facebook/react@ab18f33d...``
_UPSTREAM_RE = re.compile(r"Upstream:\s*`?([\w.\-]+/[\w.\-]+)@")
# Where a result declares the repo its content CAME FROM. Both markers are
# line-anchored and structural:
#   `# github.com/sg-evals/react--56408a5b – path/to/File.ts`   (result header)
#   `URL: https://demo.sourcegraph.com/github.com/<repo>/-/blob/...`
#
# Matching bare `github.com/...` anywhere in the body would instead scrape URLs
# out of file *content* — source and changelogs routinely link to their own
# upstream tracker — and score ordinary reads as contamination.
#   `github.com/sg-evals/ansible--379058e1 e658995...fb7dd7f...`  (diff header)
# compare_revisions/diff_search head their output with the repo followed by the
# commit range. The trailing sha is required: it is what distinguishes a diff
# header from a prose line that merely opens with a repo name.
_PROVENANCE_RES = (
    re.compile(r"^#\s*github\.com/([\w.\-]+/[\w.\-]+)", re.MULTILINE),
    re.compile(
        r"^URL:\s*https?://[^\s/]+/github\.com/([\w.\-]+/[\w.\-]+)", re.MULTILINE
    ),
    re.compile(
        r"^github\.com/([\w.\-]+/[\w.\-]+)\s+[0-9a-f]{7,}", re.MULTILINE
    ),
)

_INTERESTING_ARGS = ("repo", "repos", "symbol", "path", "query")

# Real MCP envelopes nest a handful of levels; anything past this is pathological.
_MAX_TEXT_DEPTH = 50


@dataclass(frozen=True)
class AuthorizedMirror:
    project: str
    mirror: str
    upstream: str | None


@dataclass(frozen=True)
class ToolCall:
    tool: str
    args: dict
    called_repos: tuple[str, ...]
    cited_repos: tuple[str, ...]
    leaked_repos: tuple[str, ...]


@dataclass(frozen=True)
class RunAudit:
    # No defaults: every field is supplied by audit_run. An audit built with the
    # buckets defaulted to empty would report as clean, which is the one wrong
    # answer this tool must never give.
    task: str
    mode: str
    replicate: str | None
    path: Path
    authorized: tuple[AuthorizedMirror, ...]
    calls: tuple[ToolCall, ...]
    pin_violating_cited: tuple[str, ...]
    foreign_cited: tuple[str, ...]
    pin_violating_called: tuple[str, ...]
    unparseable_lines: int
    ambiguous_projects: tuple[str, ...]

    @property
    def trustworthy(self) -> bool:
        """Whether a 'clean' verdict for this run means anything.

        An ambiguous authorized set or a partially-unread trace both make a
        no-violation result unsound rather than merely negative.
        """
        return not self.ambiguous_projects and not self.unparseable_lines

    @property
    def label(self) -> str:
        """How this run is named in the report.

        The replicate is part of the run's identity, not decoration: the rescore
        decision downstream is per-run, and two replicates of one task can
        differ in whether they were contaminated. Without it, they render as
        repeated identical lines carrying different counts.
        """
        mode = f"{self.mode}/{self.replicate}" if self.replicate else self.mode
        return f"{self.task} ({mode})"

    @property
    def scored(self) -> bool:
        """A run with no authorized set (e.g. baseline, no MCP preamble) has
        nothing to violate. Reporting it as 'clean' would dilute the MCP rate."""
        return bool(self.authorized)

    @property
    def actively_read_wrong_revision(self) -> bool:
        """Wrong-revision source actually entered the agent's context."""
        return bool(self.pin_violating_called)


def normalize_repo(raw: str) -> str:
    """Strip the host prefix and any regex anchors from a repo reference."""
    name = raw.strip().strip("`")
    name = name.removeprefix("^").removesuffix("$")
    name = name.removeprefix("https://").removeprefix("github.com/")
    return name


def _project_of_mirror(mirror: str) -> str:
    """`sg-evals/react--ab18f33d` -> `react`."""
    return mirror.removeprefix(MIRROR_PREFIX).rsplit("--", 1)[0]


def parse_authorized_mirrors(preamble: str) -> tuple[AuthorizedMirror, ...]:
    """Recover the authorized mirror set from a run's MCP preamble.

    The preamble lists one block per repo carrying the `repo:^...$` MCP filter
    and the upstream `owner/name@sha`. Both are needed: a reference can leak
    into a sibling mirror *or* into upstream HEAD, and only the upstream line
    tells us which upstream belongs to this project (matching on bare project
    basename would misfile an unrelated `preactjs/react` as a pin violation).

    An `Upstream:` line binds to the mirror of its OWN block. A mirror whose
    block carries no upstream is flushed with `upstream=None` when the next
    mirror opens — it must not swallow the following block's upstream, which a
    FIFO queue would do.
    """
    mirrors: list[AuthorizedMirror] = []
    pending: str | None = None

    def _flush(mirror: str, upstream: str | None) -> None:
        mirrors.append(
            AuthorizedMirror(
                project=_project_of_mirror(mirror), mirror=mirror, upstream=upstream
            )
        )

    for line in preamble.splitlines():
        found = _MIRROR_RE.search(line)
        if found:
            if pending is not None:  # previous block had no Upstream line
                _flush(pending, None)
            pending = found.group(1)
            continue

        upstream = _UPSTREAM_RE.search(line)
        if upstream and pending is not None:
            _flush(pending, upstream.group(1))
            pending = None

    if pending is not None:
        _flush(pending, None)
    return tuple(mirrors)


def ambiguous_projects(authorized: tuple[AuthorizedMirror, ...]) -> tuple[str, ...]:
    """Projects the preamble authorizes at more than one revision.

    Such a run has no single revision pin: a generic scoping block and a
    task-specific one can name different mirrors of the same project, and only
    one is the task's real pin. Both end up authorized, so a reference that
    escapes into the other scores AUTHORIZED — a clean verdict the tool has no
    grounds for. Ambiguity is reported, never absorbed.
    """
    by_project: dict[str, set[str]] = defaultdict(set)
    for m in authorized:
        by_project[m.project].add(m.mirror)
    return tuple(sorted(p for p, mirrors in by_project.items() if len(mirrors) > 1))


def classify_repo(repo: str, authorized: tuple[AuthorizedMirror, ...]) -> str:
    """Classify an observed repo against the run's authorized mirror set."""
    name = normalize_repo(repo)

    if any(name == m.mirror for m in authorized):
        return AUTHORIZED

    if name.startswith(MIRROR_PREFIX):
        # A sibling mirror: same project, different pinned revision.
        project = _project_of_mirror(name)
        return PIN_VIOLATING if any(project == m.project for m in authorized) else FOREIGN

    # A non-mirror repo is a pin violation only if it is the upstream of an
    # authorized project — i.e. the same code at HEAD rather than at the pin.
    return PIN_VIOLATING if any(name == m.upstream for m in authorized) else FOREIGN


def _text_of(content, depth: int = 0) -> str:
    """Flatten a result payload to text with its newlines intact.

    MCP results arrive as a JSON envelope carried inside a plain string, e.g.
    `'{"text": "# github.com/... \\n18: ..."}'`. Its newlines are escaped, so the
    envelope must be decoded before the line-anchored provenance markers can
    match — otherwise every leak is silently missed.

    Depth is bounded because the string branch re-decodes anything that *looks*
    like JSON, so a doubly-encoded envelope compounds container nesting with
    decode nesting. Unbounded, one pathological trace raises RecursionError out
    of `audit_corpus` and aborts every remaining trace in the run.
    """
    if depth > _MAX_TEXT_DEPTH:
        return ""
    if isinstance(content, str):
        head = content.lstrip()[:1]
        if head in ("{", "["):
            try:
                return _text_of(json.loads(content), depth + 1)
            except (json.JSONDecodeError, ValueError):
                return content
        return content
    if isinstance(content, dict):
        if isinstance(content.get("text"), str):
            return _text_of(content["text"], depth + 1)
        return "\n".join(_text_of(v, depth + 1) for v in content.values())
    if isinstance(content, list):
        return "\n".join(_text_of(v, depth + 1) for v in content)
    return ""


def _called_repos(args: dict) -> tuple[str, ...]:
    """Repos the agent reached into deliberately, named in the call's own args.

    Two arg shapes occur in the corpus: `repo` carries a single name, while
    `repos` (commit_search, diff_search) carries a list — which some traces
    deliver JSON-encoded as a string rather than as a real list.
    """
    raw = args.get("repo") or args.get("repos") or []
    if isinstance(raw, str) and raw.lstrip().startswith("["):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return ()
    names = [raw] if isinstance(raw, str) else raw
    if not isinstance(names, list):
        return ()
    return tuple(normalize_repo(n) for n in names if isinstance(n, str) and n)


def _cited_repos(result_text: str) -> tuple[str, ...]:
    """Repos a result declares its content came from."""
    found: set[str] = set()
    for pattern in _PROVENANCE_RES:
        found.update(normalize_repo(m) for m in pattern.findall(result_text))
    return tuple(sorted(found))


def _read_trace(path: Path) -> tuple[list[dict], int]:
    """Parse a trace, returning its records and the count of unparseable lines.

    A truncated line (a run killed mid-write) is skipped — but never silently.
    If the dropped line was the one carrying the leak evidence, discarding it
    without a word turns a contaminated run into a clean-looking one, which is
    the single result this tool must never produce. The count is surfaced in the
    report so a degraded read can never pass for a clean read.
    """
    records: list[dict] = []
    unparseable = 0
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            unparseable += 1
    return records, unparseable


def _iter_blocks(records: list[dict]):
    """Yield every structured content block of every message."""
    for rec in records:
        content = (rec.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict):
                yield block


def _preamble_text(records: list[dict]) -> str:
    """Text of user turns, excluding tool results (which quote repo names and
    would otherwise be mistaken for the authorized set)."""
    parts: list[str] = []
    for rec in records:
        if rec.get("type") != "user":
            continue
        content = (rec.get("message") or {}).get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            parts.extend(
                b.get("text", "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )
    return "\n".join(parts)


def audit_run(path: Path, root: Path | None = None) -> RunAudit:
    """Audit one agent_trace.jsonl.

    `root` is the corpus root, used to locate the task/mode segments by position
    rather than by guessing at directory names.
    """
    path = Path(path)
    records, unparseable = _read_trace(path)
    authorized = parse_authorized_mirrors(_preamble_text(records))

    uses: dict[str, tuple[str, dict]] = {}  # tool_use_id -> (tool name, input)
    results: dict[str, str] = {}  # tool_use_id -> result text
    for block in _iter_blocks(records):
        kind = block.get("type")
        if kind == "tool_use":
            tool = block.get("name", "").split("__")[-1]
            uses[block.get("id", "")] = (tool, block.get("input") or {})
        elif kind == "tool_result":
            results[block.get("tool_use_id", "")] = _text_of(block.get("content"))

    calls: list[ToolCall] = []
    for use_id, (tool, args) in uses.items():
        cited = _cited_repos(results.get(use_id, ""))
        leaked = tuple(r for r in cited if classify_repo(r, authorized) != AUTHORIZED)
        calls.append(
            ToolCall(
                tool=tool,
                args={k: v for k, v in args.items() if k in _INTERESTING_ARGS},
                called_repos=_called_repos(args),
                cited_repos=cited,
                leaked_repos=leaked,
            )
        )

    def _bucket(repos, kind: str) -> tuple[str, ...]:
        return tuple(sorted({r for r in repos if classify_repo(r, authorized) == kind}))

    all_cited = [r for c in calls for r in c.cited_repos]
    all_called = [r for c in calls for r in c.called_repos]

    task, mode = _task_and_mode(path, root)
    return RunAudit(
        task=task,
        mode=mode,
        replicate=_replicate_of(path),
        path=path,
        authorized=authorized,
        calls=tuple(calls),
        pin_violating_cited=_bucket(all_cited, PIN_VIOLATING),
        foreign_cited=_bucket(all_cited, FOREIGN),
        pin_violating_called=_bucket(all_called, PIN_VIOLATING),
        unparseable_lines=unparseable,
        ambiguous_projects=ambiguous_projects(authorized),
    )


def _replicate_of(path: Path) -> str | None:
    """`.../<mode>/repN/agent_trace.jsonl` -> `repN`; None for a plain run."""
    parent = path.parts[-2] if len(path.parts) >= 2 else ""
    return parent if _REPLICATE_DIR.fullmatch(parent) else None


def _task_and_mode(path: Path, root: Path | None = None) -> tuple[str, str]:
    """`<root>/<task>/<mode>/agent_trace.jsonl` -> (task, mode).

    Segments are counted from the corpus ROOT, not matched against a directory
    name. Keying off the literal name `runs` silently swapped task and mode for
    any corpus root called something else — and `results/runs` is gitignored, so
    re-running against an archived or renamed copy is the expected case.

    Two other shapes occur:

    - `<task>/<mode>/repN/` — a replicate is a repeat OF a mode, not a mode of
      its own. Treating `rep1` as the mode both invents a bucket that does not
      exist and strips the run of its real mode, which silently under-counts
      that mode in the rollup.
    - `<task>/` (flat, older runs) — no mode; saying so beats guessing one.
    """
    dirs = list(path.parts[:-1])
    if root is not None:
        try:
            dirs = list(path.relative_to(root).parts[:-1])
        except ValueError:  # path is not under root — fall back to the tail
            pass
    if dirs and _REPLICATE_DIR.fullmatch(dirs[-1]):
        dirs.pop()
    if not dirs:
        return ("unknown", "unknown")
    if len(dirs) < 2 or (root is None and dirs[-2] == "runs"):
        return (dirs[-1], "unknown")
    return (dirs[-2], dirs[-1])


def audit_corpus(runs_dir: Path) -> list[RunAudit]:
    root = Path(runs_dir)
    traces = sorted(
        t for t in root.rglob("agent_trace.jsonl") if INVALIDATED_DIR not in t.parts
    )
    return [audit_run(t, root) for t in traces]


def format_report(audits: list[RunAudit]) -> str:
    scored = [a for a in audits if a.scored]
    skipped = len(audits) - len(scored)

    lines = [
        "=== Mirror Contamination Audit ===",
        "",
        f"Traces found:      {len(audits)}",
        f"Scored (have an authorized mirror set): {len(scored)}",
        f"Unscored (no MCP preamble — nothing to violate): {skipped}",
        "",
        "--- Per-Mode Rollup ---",
    ]

    warnings: list[str] = []

    degraded = [a for a in audits if a.unparseable_lines]
    if degraded:
        warnings += [
            f"UNPARSEABLE LINES in {len(degraded)} trace(s) — these reads are "
            f"DEGRADED, not clean:",
            *(f"  {a.label}: {a.unparseable_lines} line(s)" for a in degraded),
            "",
        ]

    ambiguous = [a for a in scored if a.ambiguous_projects]
    if ambiguous:
        warnings += [
            f"AMBIGUOUS AUTHORIZED SET in {len(ambiguous)} run(s) — the preamble "
            "names two mirrors of one project, so there is no single revision "
            "pin. A leak into the other mirror would score AUTHORIZED: a 'clean' "
            "verdict for these runs is UNSOUND, not negative.",
            *(
                f"  {a.label}: {', '.join(a.ambiguous_projects)}"
                for a in ambiguous
            ),
            "",
        ]

    lines[4:4] = warnings

    by_mode: dict[str, list[RunAudit]] = defaultdict(list)
    for a in scored:
        by_mode[a.mode].append(a)

    for mode in sorted(by_mode):
        runs = by_mode[mode]
        cited = sum(1 for a in runs if a.pin_violating_cited)
        read = sum(1 for a in runs if a.actively_read_wrong_revision)
        bleed = sum(1 for a in runs if a.foreign_cited)
        lines.append(
            f"  {mode}: {len(runs)} runs | "
            f"wrong-rev in results: {cited} | "
            f"wrong-rev ACTIVELY READ: {read} | "
            f"foreign-repo bleed: {bleed}"
        )
    lines.append("")

    offenders = [a for a in scored if a.pin_violating_cited]
    if offenders:
        lines.append("--- Runs with wrong-revision source in results ---")
        for a in sorted(offenders, key=lambda x: (-len(x.pin_violating_cited), x.label)):
            flag = "READ" if a.actively_read_wrong_revision else "seen"
            lines.append(
                f"  [{flag}] {a.label} — "
                f"{len(a.pin_violating_cited)} wrong-rev mirror(s)"
            )
            for repo in a.pin_violating_cited:
                marker = "*" if repo in a.pin_violating_called else " "
                lines.append(f"      {marker} {repo}")
        lines.append("")
        lines.append("  (* = agent issued a tool call directly against this repo)")
        lines.append("")

    # A leaked repo is pin-violating exactly when it is in the run's
    # pin_violating_cited set, which audit_run already classified.
    leak_tools = Counter(
        c.tool
        for a in scored
        for c in a.calls
        if any(repo in a.pin_violating_cited for repo in c.leaked_repos)
    )
    if leak_tools:
        lines.append("--- Pin-violating leaks by tool ---")
        for tool, n in leak_tools.most_common():
            lines.append(f"  {tool}: {n} call(s) returned a wrong-revision repo")
        lines.append("")

    return "\n".join(lines)


def format_json(audits: list[RunAudit]) -> str:
    return json.dumps(
        {
            "traces": len(audits),
            "scored": sum(1 for a in audits if a.scored),
            "runs": [
                {
                    "task": a.task,
                    "mode": a.mode,
                    "replicate": a.replicate,
                    "path": str(a.path),
                    "authorized": [m.mirror for m in a.authorized],
                    "pin_violating_cited": list(a.pin_violating_cited),
                    "pin_violating_called": list(a.pin_violating_called),
                    "foreign_cited": list(a.foreign_cited),
                    "actively_read_wrong_revision": a.actively_read_wrong_revision,
                    "unparseable_lines": a.unparseable_lines,
                    "ambiguous_projects": list(a.ambiguous_projects),
                    "trustworthy": a.trustworthy,
                }
                for a in audits
                if a.scored
            ],
        },
        indent=2,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--runs-dir",
        required=True,
        help="Directory of run outputs (searched recursively for agent_trace.jsonl)",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    runs_dir = Path(args.runs_dir)
    if not runs_dir.is_dir():
        print(f"Error: not a directory: {runs_dir}", file=sys.stderr)
        return 1

    audits = audit_corpus(runs_dir)
    if not audits:
        print(f"Error: no agent_trace.jsonl found under {runs_dir}", file=sys.stderr)
        return 1

    print(format_json(audits) if args.as_json else format_report(audits))
    return 0


if __name__ == "__main__":
    sys.exit(main())
