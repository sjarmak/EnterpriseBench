#!/usr/bin/env python3
"""KG-based task miner: derive multi-hop cross-repo eval tasks from a
deterministically-built import graph (see kg_graph.py).

Pipeline:
  1. build_graph() over local clones of real OSS repos
  2. mine_cross_repo_paths() -> ranked N-hop cross-repo chains
  3. generate_task() -> candidate task dict conforming to schemas/task.schema.json
  4. validate_task_dict() -> JSON Schema + eb_verify semantic layer
  5. run_crnt() -> structural Cross-Repo Necessity Test

Usage:
    python3 scripts/mining/kg_task_miner.py \
        --repo httpx=/scratch/httpx --repo httpcore=/scratch/httpcore \
        --repo h11=/scratch/h11 --out /scratch/mined_task.json
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parent.parent.parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_REPO_ROOT / "lib"))
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "validation"))

import kg_graph  # noqa: E402
from kg_graph import MinedPath, RepoGraph, hop_dst_repo  # noqa: E402

_SCHEMA_PATH = _REPO_ROOT / "schemas" / "task.schema.json"

_STRATUM_BY_REPO_COUNT = {2: "dual_repo", 3: "tri_repo", 4: "multi_repo", 5: "multi_repo"}
# Calibrated against solve-verification: a 2-hop chain is a moderate task
# (schema enum: medium < hard < expert), 3+ hops is hard. 15 min per hop.
_DIFFICULTY_BY_HOPS = {2: "medium"}  # >=3 hops -> hard
_MINUTES_PER_HOP = 15
_ROLES_MIDDLE = "intermediary"

# NOTE (prototype): question text is a template keyed off path endpoints.
# An LLM curator would write a far better failure narrative here (concrete
# customer symptom, realistic error text) — see design notes.
_PROMPT_TEMPLATE = """\
A customer escalation traces a failure from {start_repo} down its real
dependency chain. The customer's code path enters at `{start_module}` in
{start_repo}, which {first_hop_clause}.

When `{start_module}` in {start_repo} fails inside that call, which {end_repo}
symbol (`{end_symbol}`, defined in `{end_module}`) ultimately implements the
behavior at the bottom of the chain?

Trace the import chain hop by hop across all {n_repos} repositories. For each
hop, cite the exact file and the verbatim import statement that carries the
dependency, then explain what `{end_symbol}` does and under what conditions a
failure there surfaces back through {start_repo}'s public API.
"""


def _sanitize(name: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")
    if not slug or not slug[0].isalpha():
        slug = f"r-{slug}" if slug else "r"
    return slug


def _first_hop_clause(hop) -> str:
    """Accurate wording for how the entry module depends on the second repo,
    keyed off the edge kind recorded by the graph builder.

    - import edge with a symbol: `from pkg import Symbol` -> "imports `Symbol`
      from repo".
    - import edge without a symbol: bare `import pkg.mod` -> "imports the
      `pkg.mod` module from repo".
    - usage edge: bare `import pkg` + `pkg.Symbol` attribute access -> names
      both the module import and the attribute use (there is no from-import).
    """
    if hop.edge_kind == "usage":
        top_module = hop.dst_module.split(".")[0]
        return (
            f"imports the `{top_module}` module from {hop.dst_repo} and "
            f"accesses `{hop.dst_symbol}` on it (`{hop.evidence.statement}`)"
        )
    if hop.dst_symbol:
        return f"imports `{hop.dst_symbol}` from {hop.dst_repo}"
    return f"imports the `{hop.dst_module}` module from {hop.dst_repo}"


def generate_task(
    path: MinedPath,
    repo_meta: dict[str, dict[str, str]],
    task_number: int = 1,
    graph: RepoGraph | None = None,
    languages: list[str] | None = None,
) -> dict[str, Any]:
    """Emit a candidate task dict conforming to schemas/task.schema.json.

    repo_meta: {repo_name: {"url": ..., "rev": ...}} for every repo on the path.
    graph: when given, glue modules and the terminal defining module are mapped
    to files for ground_truth (sufficient_files / terminal required_file).
    languages: metadata languages for the repo set; defaults to ["python"]
    (paths mined by kg_graph_go.py pass ["go"]).
    """
    repos_on_path = path.repo_chain()
    missing = [r for r in repos_on_path if r not in repo_meta]
    if missing:
        raise ValueError(f"repo_meta missing entries for path repos: {missing}")
    n_repos = len(repos_on_path)
    n_hops = len(path.hops)
    if n_repos not in _STRATUM_BY_REPO_COUNT:
        raise ValueError(f"unsupported repo count on path: {n_repos}")

    first_hop, last_hop = path.hops[0], path.hops[-1]
    start_repo, end_repo = repos_on_path[0], repos_on_path[-1]
    task_id = f"kg-{_sanitize(start_repo)}-{_sanitize(end_repo)}-{task_number:03d}"

    prompt = _PROMPT_TEMPLATE.format(
        start_repo=start_repo,
        start_module=first_hop.src_module,
        first_hop_clause=_first_hop_clause(first_hop),
        end_repo=end_repo,
        end_symbol=last_hop.dst_symbol or last_hop.dst_module,
        end_module=last_hop.dst_module,
        n_repos=n_repos,
    )

    repos = []
    for i, repo in enumerate(repos_on_path):
        role = "primary" if i == 0 else ("upstream" if i == n_repos - 1 else _ROLES_MIDDLE)
        repos.append({
            "url": repo_meta[repo]["url"],
            "rev": repo_meta[repo]["rev"],
            "path": repo,
            "role": role,
        })

    checkpoints = _checkpoints_for(path)
    required_files = _required_files_for(path, graph)
    already_required = {(f["repo"], f["path"]) for f in required_files}
    sufficient_files = [
        f for f in _sufficient_files_for(path, graph)
        if (f["repo"], f["path"]) not in already_required
    ]

    return {
        "difficulty_stratum": _STRATUM_BY_REPO_COUNT[n_repos],
        "mcp_suite": "eb_v1",
        "repo_set_id": _sanitize("-".join(repos_on_path)),
        "org_scale": n_repos >= 2,
        "verification_modes": ["deterministic"],
        "task": {
            "id": task_id,
            "suite": "customer_escalation",
            "task_type": "error_provenance",
            "difficulty": _DIFFICULTY_BY_HOPS.get(n_hops, "hard"),
            "estimated_duration_minutes": min(_MINUTES_PER_HOP * n_hops, 480),
            "session_type": "single",
            "description": (
                f"Mined {n_hops}-hop cross-repo import chain: "
                + " -> ".join(path.node_chain())
            ),
            "prompt": prompt,
        },
        "repos": repos,
        "metadata": {
            "languages": languages or ["python"],
            "dependency_depth": n_repos,
            "multi_repo_pattern": "investigate",
        },
        "checkpoints": checkpoints,
        "artifacts": {"required": ["answer"], "optional": []},
        "tool_access": {
            "expected_mcp_benefit": "high",
            "mcp_benefit_rationale": (
                f"Answering requires following a {n_hops}-hop import chain across "
                f"{n_repos} repositories ({' -> '.join(repos_on_path)}); each hop is "
                "invisible to single-repo search and was mined from verbatim import "
                "statements with file:line evidence."
            ),
        },
        "ground_truth": {
            "tiers": ["deterministic"],
            "required_files": required_files,
            **({"sufficient_files": sufficient_files} if sufficient_files else {}),
        },
    }


def _checkpoints_for(path: MinedPath) -> list[dict[str, Any]]:
    """One checkpoint per hop; each description carries the evidence tuple."""
    n = len(path.hops)
    weights = [round(1.0 / n, 4)] * n
    weights[-1] = round(1.0 - sum(weights[:-1]), 4)
    checkpoints = []
    for i, hop in enumerate(path.hops):
        ev = hop.evidence
        glue_note = ""
        if i >= 1 and i - 1 < len(path.glue_chains) and path.glue_chains[i - 1]:
            glue_note = (
                " Reached from the previous hop via intra-repo chain: "
                + " -> ".join(path.glue_chains[i - 1]) + "."
            )
        checkpoints.append({
            "name": f"hop_{i + 1}_{_sanitize(hop.src_repo)}_to_{_sanitize(hop_dst_repo(hop))}".replace("-", "_"),
            "weight": weights[i],
            "verifier": f"checks/check_hop_{i + 1}.sh",
            "description": (
                f"Agent identifies hop {i + 1}: {hop.src_node} -> {hop.dst_node}. "
                f"Evidence: repo={ev.repo}, file={ev.file}, line {ev.line}, "
                f"statement: {ev.statement}.{glue_note}"
            ),
            "timeout_seconds": 120,
            "repo_deps": [hop.src_repo, hop.dst_repo],
        })
    return checkpoints


def _file_entry(repo: str, file: str, confidence: float) -> dict[str, Any]:
    return {
        "path": f"{repo}/{file}",
        "repo": repo,
        "confidence": confidence,
        "source": "deterministic",
    }


def _required_files_for(
    path: MinedPath, graph: RepoGraph | None,
) -> list[dict[str, Any]]:
    """Evidence file of each hop, plus the file defining the terminal symbol —
    guarantees every repo on the path has at least one required file (CRNT)."""
    files: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add(repo: str, file: str) -> None:
        if (repo, file) in seen:
            return
        seen.add((repo, file))
        files.append(_file_entry(repo, file, 0.95))

    for hop in path.hops:
        add(hop.evidence.repo, hop.evidence.file)
    terminal = path.hops[-1]
    if terminal.resolved and terminal.dst_repo is not None:
        if graph is not None:
            terminal_file = graph.module_files.get(
                (terminal.dst_repo, terminal.dst_module))
        else:
            # Best-effort guess from the dotted module (fixture/offline use).
            terminal_file = (
                terminal.dst_module.split(".", 1)[-1].replace(".", "/") + ".py")
        if terminal_file:
            add(terminal.dst_repo, terminal_file)
    return files


def _sufficient_files_for(
    path: MinedPath, graph: RepoGraph | None,
) -> list[dict[str, Any]]:
    """Files of intra-repo glue modules connecting consecutive hops."""
    if graph is None:
        return []
    files: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for i, chain in enumerate(path.glue_chains):
        repo = hop_dst_repo(path.hops[i])
        for module in chain:
            file = graph.module_files.get((repo, module))
            if file and (repo, file) not in seen:
                seen.add((repo, file))
                files.append(_file_entry(repo, file, 0.75))
    return files


# ----------------------------------------------------------------------------
# Checkpoint verifier scripts
# ----------------------------------------------------------------------------

# Interface matches lib/eb_verify/runner.py and the existing benchmarks/*/checks
# convention: invoked as `bash <script>` with WORKSPACE/TASK_DIR in the env,
# prints one JSON line {"score", "passed", "detail"} on stdout (score>0 = pass),
# nonzero exit mirrors failure for standalone use.
_CHECK_SCRIPT_TEMPLATE = """\
#!/usr/bin/env bash
# Verifier for checkpoint: {checkpoint_name}
# Auto-emitted by scripts/mining/kg_task_miner.py.
# Deterministically verifies hop {hop_number} evidence: the cited file exists
# in the workspace and contains the verbatim mined statement (compared with
# whitespace normalized, so wrapped multi-line imports still match).
set -euo pipefail

WS="${{WORKSPACE:-/workspace}}"
REL={rel_path_q}
FILE="$WS/$REL"

if [[ ! -f "$FILE" ]]; then
    printf '{{"score": 0.0, "passed": false, "detail": "Evidence file missing: %s"}}\\n' "$REL"
    exit 1
fi

EB_EVIDENCE_FILE="$FILE" EB_EVIDENCE_REL="$REL" EB_STATEMENT={statement_q} \\
python3 - <<'PY'
import json
import os
import sys

content = open(os.environ["EB_EVIDENCE_FILE"], encoding="utf-8", errors="replace").read()
statement = os.environ["EB_STATEMENT"]
rel = os.environ["EB_EVIDENCE_REL"]
norm = " ".join(content.split())
norm_statement = " ".join(statement.split())
if norm_statement in norm:
    print(json.dumps({{"score": 1.0, "passed": True,
                      "detail": f"Evidence verified in {{rel}}"}}))
    sys.exit(0)
print(json.dumps({{"score": 0.0, "passed": False,
                  "detail": f"Verbatim statement not found in {{rel}}"}}))
sys.exit(1)
PY
"""


def emit_check_scripts(path: MinedPath, checks_dir: Path) -> list[Path]:
    """Write one executable check_hop_N.sh per hop into checks_dir.

    Each script verifies the hop's mined evidence against the workspace:
    workspace/{repo}/{file} exists and contains the verbatim statement.
    Hermetic — no network, no answer file, no ground-truth JSON needed.
    """
    import shlex

    checks_dir.mkdir(parents=True, exist_ok=True)
    checkpoints = _checkpoints_for(path)
    scripts: list[Path] = []
    for i, (hop, checkpoint) in enumerate(zip(path.hops, checkpoints)):
        ev = hop.evidence
        script_path = checks_dir / f"check_hop_{i + 1}.sh"
        script_path.write_text(_CHECK_SCRIPT_TEMPLATE.format(
            checkpoint_name=checkpoint["name"],
            hop_number=i + 1,
            rel_path_q=shlex.quote(f"{ev.repo}/{ev.file}"),
            statement_q=shlex.quote(ev.statement),
        ))
        script_path.chmod(0o755)
        scripts.append(script_path)
    return scripts


# ----------------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------------

def validate_task_dict(task: dict[str, Any]) -> list[str]:
    """JSON Schema (Draft 2020-12) + eb_verify semantic-layer validation.
    Returns a list of error strings; empty list = valid."""
    import jsonschema
    from eb_verify.schema_validator import _validate_semantic_layer

    with open(_SCHEMA_PATH) as f:
        schema = json.load(f)
    errors: list[str] = []
    validator = jsonschema.Draft202012Validator(schema)
    for err in validator.iter_errors(task):
        loc = ".".join(str(p) for p in err.absolute_path) or "(root)"
        errors.append(f"schema:{loc}: {err.message}")
    sem_errors, _warnings = _validate_semantic_layer(task)
    errors.extend(f"semantic:{e.field}: {e.message}" for e in sem_errors)
    return errors


def run_crnt(task: dict[str, Any]):
    """Structural Cross-Repo Necessity Test via scripts/validation/crnt_validator."""
    import crnt_validator
    return crnt_validator.evaluate_crnt(task)


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def _render_hops(path: MinedPath) -> list[str]:
    """Node chain for display, annotating the hop source module whenever it
    differs from the previous landing module (intra-repo glue) — otherwise
    structurally distinct groups can print identical chains."""
    parts = [path.hops[0].src_node]
    for i, hop in enumerate(path.hops):
        prev = path.hops[i - 1]
        if i and (hop.src_repo, hop.src_module) != (prev.dst_repo, prev.dst_module):
            parts.append(f"(via {hop.src_repo}:{hop.src_module})")
        parts.append(hop.dst_node)
    return parts


def _git_meta(repo_dir: Path) -> dict[str, str]:
    def run(*args: str) -> str:
        out = subprocess.run(
            ["git", "-C", str(repo_dir), *args],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    return {"url": run("remote", "get-url", "origin"), "rev": run("rev-parse", "HEAD")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo", action="append", required=True, metavar="NAME=PATH",
        help="repo name and local clone path (repeatable)",
    )
    parser.add_argument("--out", type=Path, help="write best mined task JSON here")
    parser.add_argument("--top", type=int, default=10, help="paths to report")
    parser.add_argument("--max-hops", type=int, default=4)
    args = parser.parse_args(argv)

    repos: dict[str, Path] = {}
    for spec in args.repo:
        if "=" not in spec:
            parser.error(f"--repo expects NAME=PATH, got: {spec}")
        name, _, path = spec.partition("=")
        repos[name] = Path(path)

    graph = kg_graph.build_graph(repos)
    cross_edges = [e for e in graph.edges if e.crosses_repo]
    print(f"nodes: {graph.node_count()}  edges: {len(graph.edges)}  "
          f"cross-repo edges: {len(cross_edges)}  parse errors: {len(graph.parse_errors)}")
    for repo, mods in sorted(graph.modules.items()):
        n_defs = sum(len(v) for k, v in graph.defs.items() if v and v[0].repo == repo)
        print(f"  {repo}: {len(mods)} modules, {n_defs} symbol groups")

    paths = kg_graph.mine_cross_repo_paths(graph, min_hops=2, max_hops=args.max_hops)
    by_hops: dict[int, int] = {}
    for p in paths:
        by_hops[len(p.hops)] = by_hops.get(len(p.hops), 0) + 1
    print(f"mined paths: {len(paths)}  by hop count: {by_hops}")

    if not paths:
        print("no cross-repo multi-hop paths found", file=sys.stderr)
        return 1

    group_sizes: dict[tuple[str, ...], int] = {}
    for p in paths:
        sig = kg_graph.structural_signature(p)
        group_sizes[sig] = group_sizes.get(sig, 0) + 1
    print(f"structural groups: {len(group_sizes)} "
          f"(sizes: {sorted(group_sizes.values(), reverse=True)})")

    selected = kg_graph.select_diverse(paths, args.top)
    print(f"\ntop {len(selected)} paths (one per structural group, "
          f"overflow after {len(group_sizes)}):")
    for p in selected:
        sig = kg_graph.structural_signature(p)
        group_idx = list(group_sizes).index(sig) + 1
        print(f"  [{kg_graph.score_path(p):6.1f}] g{group_idx:02d} "
              + "  ->  ".join(_render_hops(p)))

    repo_meta = {name: _git_meta(path) for name, path in repos.items()}
    task = generate_task(selected[0], repo_meta, graph=graph)
    errors = validate_task_dict(task)
    if errors:
        print("\nVALIDATION FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 2
    print("\nschema + semantic validation: PASS")

    crnt = run_crnt(task)
    print(f"CRNT: {'PASS' if crnt.passes_crnt else 'FAIL'} "
          f"(repos={crnt.num_repos}, uncovered={list(crnt.uncovered_repos)})")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w") as f:
            json.dump(task, f, indent=2)
        print(f"wrote {args.out}")
        scripts = emit_check_scripts(selected[0], args.out.parent / "checks")
        print(f"wrote {len(scripts)} checkpoint verifiers under "
              f"{args.out.parent / 'checks'}")
    return 0 if crnt.passes_crnt else 3


if __name__ == "__main__":
    sys.exit(main())
