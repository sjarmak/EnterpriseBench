"""Deterministic dependency/import knowledge graph over a set of Python repos.

Builds nodes and edges purely from `ast` parsing — no LLM calls, no imports of
the analyzed code. Canonical node ids are `repo:module.symbol` (symbol nodes)
or `repo:module` (module nodes). Symbols imported through a package __init__
re-export are canonicalized to the module that actually DEFINES them when that
resolution is unambiguous.

Also mines N-hop cross-repo paths: chains of import edges where every hop
crosses a repo boundary, each hop carrying {repo, file, line, statement}
evidence.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

# Directory names never scanned for packages or sources.
_SKIP_DIRS = {
    ".git", ".tox", ".venv", "venv", "node_modules", "__pycache__",
    "tests", "test", "docs", "examples", "scripts", "benchmarks",
}


@dataclass(frozen=True)
class Evidence:
    """Verbatim provenance for one import edge."""
    repo: str
    file: str  # path relative to repo root, posix-style
    line: int
    statement: str


@dataclass(frozen=True)
class SymbolDef:
    repo: str
    module: str
    name: str
    kind: str  # "class" | "function"
    file: str
    line: int

    @property
    def node_id(self) -> str:
        return f"{self.repo}:{self.module}.{self.name}"


@dataclass(frozen=True)
class ImportEdge:
    src_repo: str
    src_module: str
    dst_repo: str | None  # None = external (stdlib / unmapped third party)
    dst_module: str  # resolved defining module when unambiguous, else as written
    dst_symbol: str | None  # None for bare `import x`
    dst_kind: str | None  # "class"/"function" when resolved to a definition
    resolved: bool  # True when canonicalized to the defining module
    evidence: Evidence
    edge_kind: str = "import"  # "import" | "usage" (attribute access on a bare import)

    @property
    def src_node(self) -> str:
        return f"{self.src_repo}:{self.src_module}"

    @property
    def dst_node(self) -> str:
        repo = self.dst_repo if self.dst_repo is not None else "external"
        if self.dst_symbol:
            return f"{repo}:{self.dst_module}.{self.dst_symbol}"
        return f"{repo}:{self.dst_module}"

    @property
    def crosses_repo(self) -> bool:
        return self.dst_repo is not None and self.dst_repo != self.src_repo

def hop_dst_repo(hop: ImportEdge) -> str:
    """Single narrowing point for the MinedPath invariant: every hop of a
    MinedPath is a cross-repo edge (mine_cross_repo_paths builds chains only
    from edges with crosses_repo), so dst_repo is always a repo name."""
    if hop.dst_repo is None:
        raise AssertionError(
            f"cross-repo hop {hop.src_node} -> {hop.dst_node} has dst_repo=None"
        )
    return hop.dst_repo


@dataclass
class RepoGraph:
    repos: dict[str, Path]
    packages: dict[str, str]  # top-level package name -> repo name
    modules: dict[str, set[str]]  # repo -> module names
    package_modules: set[tuple[str, str]]  # (repo, module) that are packages
    defs: dict[tuple[str, str], list[SymbolDef]]  # (repo, symbol) -> defs
    module_files: dict[tuple[str, str], str] = field(default_factory=dict)
    edges: list[ImportEdge] = field(default_factory=list)
    parse_errors: list[tuple[str, str, str]] = field(default_factory=list)

    def node_count(self) -> int:
        module_nodes = sum(len(m) for m in self.modules.values())
        symbol_nodes = sum(len(v) for v in self.defs.values())
        return module_nodes + symbol_nodes


@dataclass(frozen=True)
class MinedPath:
    """A chain of cross-repo import edges. Hop i+1 sources from a module in
    hop i's target repo that is reachable from the landing module through
    intra-repo imports; that intra-repo module chain (possibly empty) is
    recorded per transition in glue_chains."""
    hops: tuple[ImportEdge, ...]
    glue_chains: tuple[tuple[str, ...], ...] = ()  # len == len(hops) - 1

    def repo_chain(self) -> tuple[str, ...]:
        chain = [self.hops[0].src_repo]
        chain.extend(hop_dst_repo(h) for h in self.hops)
        return tuple(chain)

    def node_chain(self) -> tuple[str, ...]:
        return (self.hops[0].src_node,) + tuple(h.dst_node for h in self.hops)


def _discover_packages(repo_root: Path) -> dict[str, Path]:
    """Top-level importable packages of a repo: dirs with __init__.py directly
    under the repo root or under root/src."""
    if not repo_root.is_dir():
        raise FileNotFoundError(f"repo root does not exist: {repo_root}")
    packages: dict[str, Path] = {}
    candidates = [repo_root]
    if (repo_root / "src").is_dir():
        candidates.append(repo_root / "src")
    for base in candidates:
        for child in sorted(base.iterdir()):
            if (
                child.is_dir()
                and child.name not in _SKIP_DIRS
                and not child.name.startswith(".")
                and (child / "__init__.py").is_file()
            ):
                packages[child.name] = child
    return packages


def _module_name(py_file: Path, pkg_dir: Path, pkg_name: str) -> tuple[str, bool]:
    """Dotted module name for a source file. Returns (module, is_package)."""
    rel = py_file.relative_to(pkg_dir)
    parts = [pkg_name] + list(rel.parts)
    if parts[-1] == "__init__.py":
        return ".".join(parts[:-1]), True
    parts[-1] = parts[-1][:-3]  # strip .py
    return ".".join(parts), False


def _iter_py_files(pkg_dir: Path):
    for path in sorted(pkg_dir.rglob("*.py")):
        if any(part in _SKIP_DIRS for part in path.relative_to(pkg_dir).parts[:-1]):
            continue
        yield path


def _statement_text(source: str, node: ast.stmt) -> str:
    seg = ast.get_source_segment(source, node)
    if seg is None:
        # Fallback: single source line (should not happen with CPython >= 3.8).
        seg = source.splitlines()[node.lineno - 1]
    return " ".join(seg.split())


def _relative_base(src_module: str, is_package: bool, level: int) -> str | None:
    """Base module of a relative import: `from .x import y` (level=1) inside
    module a.b.c resolves against package a.b."""
    parts = src_module.split(".")
    if not is_package:
        parts = parts[:-1]  # containing package of a plain module
    drop = level - 1
    if drop >= len(parts):
        return None
    if drop:
        parts = parts[:-drop]
    return ".".join(parts) if parts else None


def build_graph(repos: dict[str, Path]) -> RepoGraph:
    """Two-pass build: (1) package/module/def discovery, (2) import edges."""
    if not repos:
        raise ValueError("repos must be a non-empty {name: root_path} mapping")

    packages: dict[str, str] = {}
    modules: dict[str, set[str]] = {r: set() for r in repos}
    package_modules: set[tuple[str, str]] = set()
    defs: dict[tuple[str, str], list[SymbolDef]] = {}
    graph = RepoGraph(
        repos=dict(repos), packages=packages, modules=modules,
        package_modules=package_modules, defs=defs,
    )

    # Pass 1: discover packages, modules, and top-level symbol definitions.
    trees: dict[tuple[str, str], tuple[ast.Module, str, str]] = {}
    for repo_name, root in repos.items():
        root = Path(root)
        for pkg_name, pkg_dir in _discover_packages(root).items():
            if pkg_name in packages and packages[pkg_name] != repo_name:
                raise ValueError(
                    f"package name collision: '{pkg_name}' in both "
                    f"'{packages[pkg_name]}' and '{repo_name}'"
                )
            packages[pkg_name] = repo_name
            for py_file in _iter_py_files(pkg_dir):
                rel_file = py_file.relative_to(root).as_posix()
                try:
                    source = py_file.read_text(encoding="utf-8", errors="replace")
                    tree = ast.parse(source, filename=str(py_file))
                except SyntaxError as exc:
                    graph.parse_errors.append((repo_name, rel_file, str(exc)))
                    continue
                module, is_pkg = _module_name(py_file, pkg_dir, pkg_name)
                modules[repo_name].add(module)
                graph.module_files[(repo_name, module)] = rel_file
                if is_pkg:
                    package_modules.add((repo_name, module))
                trees[(repo_name, module)] = (tree, source, rel_file)
                for stmt in tree.body:
                    if isinstance(stmt, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                        kind = "class" if isinstance(stmt, ast.ClassDef) else "function"
                        defs.setdefault((repo_name, stmt.name), []).append(
                            SymbolDef(
                                repo=repo_name, module=module, name=stmt.name,
                                kind=kind, file=rel_file, line=stmt.lineno,
                            )
                        )

    # Pass 2: import edges with symbol canonicalization, plus attribute-usage
    # edges for bare `import pkg` bindings (pkg.Symbol at a usage site).
    for (repo_name, module), (tree, source, rel_file) in trees.items():
        is_pkg = (repo_name, module) in package_modules
        bindings: dict[str, str] = {}  # local name -> imported module
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    graph.edges.append(_edge_for_plain_import(
                        graph, repo_name, module, alias.name,
                        Evidence(repo_name, rel_file, node.lineno,
                                 _statement_text(source, node)),
                    ))
                    local = alias.asname or alias.name.split(".")[0]
                    bindings[local] = alias.name if alias.asname else alias.name.split(".")[0]
            elif isinstance(node, ast.ImportFrom):
                target_module = _import_from_target(
                    graph, repo_name, module, is_pkg, node)
                if target_module is None:
                    continue
                ev = Evidence(repo_name, rel_file, node.lineno,
                              _statement_text(source, node))
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    graph.edges.append(_edge_for_symbol_import(
                        graph, repo_name, module, target_module, alias.name, ev))
        graph.edges.extend(_usage_edges(
            graph, repo_name, module, tree, source, rel_file, bindings))
    return graph


def _usage_edges(
    graph: RepoGraph, repo_name: str, module: str, tree: ast.Module,
    source: str, rel_file: str, bindings: dict[str, str],
) -> list[ImportEdge]:
    """Symbol-level edges from attribute access on bare-imported modules:
    `import h11` + `h11.Connection(...)` -> edge to h11's Connection with the
    usage line as evidence. Deduplicated per (target module, symbol), keeping
    the first occurrence by line number."""
    known = {
        name: target for name, target in bindings.items()
        if _repo_for_module(graph, target) is not None
    }
    if not known:
        return []
    lines = source.splitlines()
    best: dict[tuple[str, str], int] = {}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in known
        ):
            key = (known[node.value.id], node.attr)
            if key not in best or node.lineno < best[key]:
                best[key] = node.lineno
    edges: list[ImportEdge] = []
    for (target_module, symbol), lineno in sorted(best.items(), key=lambda kv: kv[1]):
        dst_repo = _repo_for_module(graph, target_module)
        assert dst_repo is not None  # filtered via `known`
        resolved_module, kind, resolved = _canonicalize_symbol(
            graph, dst_repo, target_module, symbol)
        statement = lines[lineno - 1].strip() if lineno <= len(lines) else ""
        edges.append(ImportEdge(
            src_repo=repo_name, src_module=module, dst_repo=dst_repo,
            dst_module=resolved_module, dst_symbol=symbol, dst_kind=kind,
            resolved=resolved,
            evidence=Evidence(repo_name, rel_file, lineno, statement[:160]),
            edge_kind="usage",
        ))
    return edges


def _repo_for_module(graph: RepoGraph, dotted: str) -> str | None:
    return graph.packages.get(dotted.split(".")[0])


def _edge_for_plain_import(
    graph: RepoGraph, src_repo: str, src_module: str, target: str, ev: Evidence,
) -> ImportEdge:
    dst_repo = _repo_for_module(graph, target)
    return ImportEdge(
        src_repo=src_repo, src_module=src_module, dst_repo=dst_repo,
        dst_module=target, dst_symbol=None, dst_kind=None,
        resolved=dst_repo is not None, evidence=ev,
    )


def _import_from_target(
    graph: RepoGraph, src_repo: str, src_module: str, is_pkg: bool,
    node: ast.ImportFrom,
) -> str | None:
    """Absolute or relative `from X import ...` -> dotted target module."""
    if node.level == 0:
        return node.module  # absolute; None never occurs at level 0
    base = _relative_base(src_module, is_pkg, node.level)
    if base is None:
        return None  # relative import escaping the package: malformed source
    return f"{base}.{node.module}" if node.module else base


def _edge_for_symbol_import(
    graph: RepoGraph, src_repo: str, src_module: str,
    target_module: str, symbol: str, ev: Evidence,
) -> ImportEdge:
    dst_repo = _repo_for_module(graph, target_module)
    if dst_repo is None:
        return ImportEdge(
            src_repo=src_repo, src_module=src_module, dst_repo=None,
            dst_module=target_module, dst_symbol=symbol, dst_kind=None,
            resolved=False, evidence=ev,
        )
    # `from pkg import sub` where pkg.sub is a module, not a symbol.
    candidate = f"{target_module}.{symbol}"
    if candidate in graph.modules[dst_repo]:
        return ImportEdge(
            src_repo=src_repo, src_module=src_module, dst_repo=dst_repo,
            dst_module=candidate, dst_symbol=None, dst_kind=None,
            resolved=True, evidence=ev,
        )
    module, kind, resolved = _canonicalize_symbol(graph, dst_repo, target_module, symbol)
    return ImportEdge(
        src_repo=src_repo, src_module=src_module, dst_repo=dst_repo,
        dst_module=module, dst_symbol=symbol, dst_kind=kind,
        resolved=resolved, evidence=ev,
    )


def _canonicalize_symbol(
    graph: RepoGraph, repo: str, imported_module: str, symbol: str,
) -> tuple[str, str | None, bool]:
    """Map (module-as-imported, symbol) to the module that DEFINES the symbol.

    Preference order: defined in the imported module itself; else defined in
    exactly one module of the repo. Ambiguous or unknown symbols keep the
    module as written and are flagged unresolved.
    """
    candidates = graph.defs.get((repo, symbol), [])
    in_imported = [d for d in candidates if d.module == imported_module]
    if in_imported:
        return imported_module, in_imported[0].kind, True
    if len({d.module for d in candidates}) == 1:
        return candidates[0].module, candidates[0].kind, True
    return imported_module, None, False


# ----------------------------------------------------------------------------
# Path mining
# ----------------------------------------------------------------------------

def _intra_adjacency(graph: RepoGraph) -> dict[tuple[str, str], set[str]]:
    """Intra-repo module adjacency from resolved intra-repo import edges."""
    adj: dict[tuple[str, str], set[str]] = {}
    for e in graph.edges:
        if (
            e.dst_repo is not None
            and e.dst_repo == e.src_repo
            and e.dst_module != e.src_module
            and e.dst_module in graph.modules[e.src_repo]
        ):
            adj.setdefault((e.src_repo, e.src_module), set()).add(e.dst_module)
    return adj


def _glue_reachable(
    adj: dict[tuple[str, str], set[str]], repo: str, start: str, depth: int,
) -> dict[str, tuple[str, ...]]:
    """BFS over intra-repo imports from `start`, bounded by `depth`.
    Returns {module: shortest intra-repo module chain from start (exclusive
    of start, inclusive of module; () for start itself)}."""
    reached: dict[str, tuple[str, ...]] = {start: ()}
    frontier = [start]
    for _ in range(depth):
        nxt: list[str] = []
        for mod in frontier:
            for neigh in sorted(adj.get((repo, mod), ())):
                if neigh not in reached:
                    reached[neigh] = reached[mod] + (neigh,)
                    nxt.append(neigh)
        frontier = nxt
    return reached


def mine_cross_repo_paths(
    graph: RepoGraph, min_hops: int = 2, max_hops: int = 4, glue_depth: int = 3,
) -> list[MinedPath]:
    """All repo-wise-simple chains of cross-repo edges with
    min_hops <= len <= max_hops, ranked best-first deterministically.

    Hop i+1 may source from any module of hop i's target repo reachable from
    the landing module via <= glue_depth intra-repo imports; the glue module
    chain is recorded per transition."""
    if min_hops < 2:
        raise ValueError("min_hops must be >= 2 (multi-hop is the point)")
    cross = [e for e in graph.edges if e.crosses_repo]
    by_src: dict[tuple[str, str], list[ImportEdge]] = {}
    for e in cross:
        by_src.setdefault((e.src_repo, e.src_module), []).append(e)
    adj = _intra_adjacency(graph)

    paths: list[MinedPath] = []

    def extend(
        hops: list[ImportEdge],
        glue: list[tuple[str, ...]],
        seen_repos: set[str],
    ) -> None:
        if min_hops <= len(hops):
            paths.append(MinedPath(hops=tuple(hops), glue_chains=tuple(glue)))
        if len(hops) >= max_hops:
            return
        tail = hops[-1]
        landing_repo = hop_dst_repo(tail)
        reachable = _glue_reachable(adj, landing_repo, tail.dst_module, glue_depth)
        for mod, chain in sorted(reachable.items()):
            for nxt in by_src.get((landing_repo, mod), []):
                if nxt.dst_repo in seen_repos:
                    continue
                extend(hops + [nxt], glue + [chain],
                       seen_repos | {hop_dst_repo(nxt)})

    for e in cross:
        extend([e], [], {e.src_repo, hop_dst_repo(e)})

    paths.sort(key=lambda p: (-score_path(p), p.node_chain()))
    return paths


def structural_signature(path: MinedPath) -> tuple[str, ...]:
    """Module-level shape of a path: (start module, hop-1 target module,
    hop-2 source module, hop-2 target module, ..., hop-N source module).

    From hop 2 on, the source module may differ from the previous landing
    module when intra-repo glue was used. Symbols and the terminal hop's
    target module are excluded, so paths that differ only in which symbol
    (or terminal module) they end on collapse into one group."""
    parts = [path.hops[0].src_node]
    for i, hop in enumerate(path.hops):
        if i:
            parts.append(f"{hop.src_repo}:{hop.src_module}")
        if i < len(path.hops) - 1:
            parts.append(f"{hop.dst_repo}:{hop.dst_module}")
    return tuple(parts)


def select_diverse(paths: list[MinedPath], top_n: int) -> list[MinedPath]:
    """Pick up to top_n paths, one representative per structural group first.

    `paths` must already be ranked best-first (mine_cross_repo_paths output).
    Groups are ranked by their best member; each group's representative is
    that best member. Only once every group is represented does selection
    overflow into second (then third, ...) representatives, again in group
    order. Pure arithmetic on the existing deterministic ranking."""
    if top_n <= 0:
        return []
    groups: dict[tuple[str, ...], list[MinedPath]] = {}
    for path in paths:
        groups.setdefault(structural_signature(path), []).append(path)
    ordered_groups = list(groups.values())  # insertion order == group rank

    selected: list[MinedPath] = []
    rank_within_group = 0
    while len(selected) < top_n:
        added = False
        for group in ordered_groups:
            if rank_within_group < len(group):
                selected.append(group[rank_within_group])
                added = True
                if len(selected) == top_n:
                    return selected
        if not added:
            return selected
        rank_within_group += 1
    return selected


def score_path(path: MinedPath) -> float:
    """Deterministic ranking: more hops, resolved named public symbols, and
    deeper (non-__init__) modules score higher; private symbols and long glue
    detours score lower. Transparent arithmetic with explicit tiebreakers —
    no semantic judgment."""
    score = 10.0 * len(path.hops)
    for hop in path.hops:
        if hop.dst_symbol:
            score += 1.0
            if hop.resolved:
                score += 3.0
            if hop.dst_kind is not None:
                score += 1.0
            if hop.dst_symbol.startswith("_"):
                score -= 2.0
        score += min(hop.dst_module.count("."), 3) * 0.5
    for chain in path.glue_chains:
        score -= 0.75 * len(chain)
    return score
