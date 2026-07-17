"""Every answer-key file's `repo` must name a repo the task actually mounts.

Ground truth stores the source-file set twice — once in `task.toml`'s
`[[ground_truth.required_files]]` (read by check_repo_staleness) and once in
`ground_truth.json` (read by the scorer). Each entry carries a `repo` label that
is meant to join the task's declared `[[repos]].path`, i.e. the directory the
repo is cloned into at `/workspace/{path}/`. A label that joins nothing points
the consumer at a mount that does not exist.

err-provenance-dual-docker-001 (EnterpriseBench-ilgxg) mounted docker/cli at
`path="docker-cli"` but its ground_truth.json labelled a required file
`repo="cli"`. That joins no sibling `[[repos]].path`, so a repo-aware matcher
would look under `/workspace/cli/` and miss the mount entirely. It stayed inert
only because the current matcher is repo-blind (EnterpriseBench-d900w); fixing
d900w makes this label load-bearing, so the join has to hold offline first.

This is the guard d900w cannot supply on its own: a leading-path-component check
(`components[0] == "cli"`) passes while still naming a repo that is not mounted.
Only an explicit repo -> `[[repos]].path` join catches it. Purely structural and
offline — no pinned-rev fetch — so it runs on every task in the tree.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
BENCHMARKS = REPO_ROOT / "benchmarks"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "validation"))
from validate_expected_solutions import _parse_toml  # noqa: E402

_FILE_GROUPS = ("required_files", "sufficient_files")


def _mounted_paths(container: dict[str, Any]) -> set[str]:
    """The `path` of every declared repo mount in a task.toml or ground_truth.json."""
    return {
        repo["path"]
        for repo in container.get("repos") or []
        if isinstance(repo, dict) and isinstance(repo.get("path"), str)
    }


def _entries(container: dict[str, Any]) -> list[tuple[str, dict]]:
    """(group, entry) pairs across both file groups, entries that are dicts."""
    out: list[tuple[str, dict]] = []
    for group in _FILE_GROUPS:
        for entry in container.get(group) or []:
            if isinstance(entry, dict):
                out.append((group, entry))
    return out


_EXCLUDED_DIRS = frozenset({"_archived", "mined"})


def _active_task_dirs() -> list[Path]:
    """Task dirs under benchmarks/, excluding the retired _archived / mined trees.

    Same exclusion set as the sibling integrity guards
    (test_required_files_evidence_nonprompt, test_scoring_evidence_is_nonprompt).
    """
    dirs = []
    for toml_path in BENCHMARKS.rglob("task.toml"):
        if _EXCLUDED_DIRS & set(toml_path.relative_to(BENCHMARKS).parts):
            continue
        dirs.append(toml_path.parent)
    return sorted(dirs)


def _label_problems(source: str, gt: dict[str, Any], mounted: set[str]) -> list[str]:
    """Entries in `gt` whose `repo` label joins no mounted [[repos]].path."""
    return [
        f"{source} {group}: repo={entry['repo']!r} (path={entry.get('path')!r}) "
        f"joins none of {sorted(mounted)}"
        for group, entry in _entries(gt)
        if entry.get("repo") is not None and entry["repo"] not in mounted
    ]


def _violations(task_dir: Path) -> list[str]:
    """Repo labels in either copy that join no declared [[repos]].path."""
    toml = _parse_toml(task_dir / "task.toml")
    # task.toml [[repos]] is the sole authority on what actually gets cloned into
    # /workspace/{path}/ — ground_truth.json's own "repos" block is a passive copy
    # and cannot mount anything. Every repo label in either copy must join THIS set.
    mounted = _mounted_paths(toml)

    problems = _label_problems("task.toml", toml.get("ground_truth") or {}, mounted)

    json_path = task_dir / "ground_truth.json"
    if json_path.exists():
        gt = json.loads(json_path.read_text(encoding="utf-8"))
        # The JSON copy's own repos block must not declare a mount task.toml lacks:
        # validating entries against a union of both would let a stale/wrong JSON
        # repos block manufacture its own pass — the exact drift this guard exists
        # to catch. So flag the drift, and check entries against `mounted` only.
        problems += [
            f"ground_truth.json repos: declares mount path={extra!r} that "
            f"task.toml [[repos]] never clones ({sorted(mounted)})"
            for extra in sorted(_mounted_paths(gt) - mounted)
        ]
        problems += _label_problems("ground_truth.json", gt, mounted)

    return problems


@pytest.mark.parametrize(
    "task_dir",
    _active_task_dirs(),
    ids=lambda d: str(d.relative_to(BENCHMARKS)),
)
def test_required_files_repo_joins_a_mount(task_dir: Path) -> None:
    problems = _violations(task_dir)
    assert not problems, (
        f"{task_dir.relative_to(BENCHMARKS)}: answer-key repo label joins no "
        f"mounted [[repos]].path — the consumer points at a repo the task never "
        f"clones:\n  " + "\n  ".join(problems)
    )


def test_docker_required_files_repo_label_is_mounted() -> None:
    """The ilgxg regression, pinned so it fails offline if the label regresses.

    docker/cli mounts at path="docker-cli"; a required file labelled repo="cli"
    joins nothing. Both copies must carry the mounted label.
    """
    task_dir = BENCHMARKS / "customer_escalation/err-provenance-dual-docker-001"

    assert not _violations(task_dir)

    # The actual regression: the stale repo="cli" label must be gone. The full
    # legal mount set is left to the parametrized join check above rather than
    # restated here, so a benign future mount rename doesn't break this pin.
    gt = json.loads((task_dir / "ground_truth.json").read_text())
    assert "cli" not in {e["repo"] for _, e in _entries(gt)}
