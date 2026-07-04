"""Deterministic Go import/usage knowledge graph over a set of Go repos.

Prototype counterpart of kg_graph.py for Go codebases. Builds the SAME
dataclasses (RepoGraph, ImportEdge, Evidence, SymbolDef) purely from text
parsing — no LLM calls, no `go` toolchain, no network — so
kg_graph.mine_cross_repo_paths, structural grouping, and the task miner
consume the result unchanged.

Vocabulary mapping onto kg_graph's Python-shaped fields:
  graph.packages : go.mod module path -> repo name (multi-module repos
                   contribute one entry per nested go.mod, etcd-style)
  "module"       : package import path (module path + relative directory)
  "symbol"       : exported top-level func ("function") / type ("class")

Edges:
  import edges  : one per import spec in a file (block or single form),
                  evidence = verbatim import line with file:line
  usage edges   : `pkg.Symbol` attribute usage after an import, respecting
                  aliases; blank (`_`) and dot (`.`) imports never bind.
                  Resolution is Go-semantic: the import path IS the defining
                  package — a symbol is "resolved" only when a top-level
                  definition was found in that exact package (no cross-module
                  re-export guessing, which Go does not have).

Known prototype limits (documented, not silently handled):
  - Symbols are regex-parsed: only top-level `func Name(` / `type Name` are
    indexed. Vars, consts, methods, and grouped `type (...)` blocks are not,
    so usages of those stay unresolved (edge kept, resolved=False).
  - A package whose name differs from its directory (e.g. gopkg.in/yaml.v2
    -> package yaml) binds under the directory-derived name unless aliased;
    `/vN` major-version suffixes are skipped per Go convention.
  - Usage scanning strips `//` and `/* */` comments but not string literals,
    so `pkg.Symbol` inside a string can create a false usage edge.
  - Files guarded by build tags are parsed like any other file.
"""
from __future__ import annotations

import re
from pathlib import Path

from kg_graph import Evidence, ImportEdge, RepoGraph, SymbolDef

_SKIP_DIRS = {".git", "vendor", "testdata", "node_modules"}

_MODULE_RE = re.compile(r"^module\s+(\S+)", re.MULTILINE)
_IMPORT_SINGLE_RE = re.compile(r'^\s*import\s+(?:(\w+|\.|_)\s+)?"([^"]+)"')
_IMPORT_BLOCK_START_RE = re.compile(r"^\s*import\s*\(")
_IMPORT_SPEC_RE = re.compile(r'^\s*(?:(\w+|\.|_)\s+)?"([^"]+)"')
_FUNC_RE = re.compile(r"^func\s+([A-Za-z_]\w*)\s*[(\[]")
_TYPE_RE = re.compile(r"^type\s+([A-Za-z_]\w*)\b")
_VERSION_SEGMENT_RE = re.compile(r"v\d+")


def _binding_name(import_path: str) -> str:
    """Local name an unaliased import binds to: the last path segment,
    skipping a `/vN` major-version suffix (Go module convention)."""
    segments = import_path.rstrip("/").split("/")
    if len(segments) > 1 and _VERSION_SEGMENT_RE.fullmatch(segments[-1]):
        return segments[-2]
    return segments[-1]


def _discover_go_modules(repo_root: Path) -> list[tuple[str, Path]]:
    """(module path, module dir) for every go.mod in the repo, outside
    skipped dirs. Raises when the repo has no go.mod at all."""
    if not repo_root.is_dir():
        raise FileNotFoundError(f"repo root does not exist: {repo_root}")
    modules: list[tuple[str, Path]] = []
    for gomod in sorted(repo_root.rglob("go.mod")):
        rel_parts = gomod.relative_to(repo_root).parts[:-1]
        if any(p in _SKIP_DIRS for p in rel_parts):
            continue
        match = _MODULE_RE.search(gomod.read_text(encoding="utf-8", errors="replace"))
        if match:
            modules.append((match.group(1), gomod.parent))
    if not modules:
        raise ValueError(f"no go.mod with a module directive under {repo_root}")
    return modules


def _package_import_path(
    go_dir: Path, module_dirs: list[tuple[str, Path]],
) -> str | None:
    """Import path of the package in go_dir: nearest enclosing go.mod module
    path + the directory's path relative to that module root."""
    best: tuple[str, Path] | None = None
    for mod_path, mod_dir in module_dirs:
        if go_dir == mod_dir or mod_dir in go_dir.parents:
            if best is None or len(mod_dir.parts) > len(best[1].parts):
                best = (mod_path, mod_dir)
    if best is None:
        return None
    mod_path, mod_dir = best
    rel = go_dir.relative_to(mod_dir).as_posix()
    return mod_path if rel == "." else f"{mod_path}/{rel}"


def _repo_for_import_path(packages: dict[str, str], import_path: str) -> str | None:
    """Longest segment-boundary prefix match of an import path against the
    known module paths. None = stdlib / unmapped third party."""
    best: str | None = None
    best_len = -1
    for mod_path, repo in packages.items():
        if import_path == mod_path or import_path.startswith(mod_path + "/"):
            if len(mod_path) > best_len:
                best, best_len = repo, len(mod_path)
    return best


def _iter_go_files(repo_root: Path):
    for path in sorted(repo_root.rglob("*.go")):
        rel_parts = path.relative_to(repo_root).parts[:-1]
        if any(p in _SKIP_DIRS for p in rel_parts):
            continue
        if path.name.endswith("_test.go"):
            continue
        yield path


def _parse_imports(lines: list[str]) -> list[tuple[str | None, str, int]]:
    """(alias-or-None, import path, 1-based line) per import spec. Handles
    the single form and `import ( ... )` blocks; comment-only lines inside a
    block are skipped."""
    specs: list[tuple[str | None, str, int]] = []
    in_block = False
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if in_block:
            if stripped.startswith(")"):
                in_block = False
                continue
            if not stripped or stripped.startswith("//"):
                continue
            m = _IMPORT_SPEC_RE.match(line)
            if m:
                specs.append((m.group(1), m.group(2), i))
            continue
        if _IMPORT_BLOCK_START_RE.match(line):
            in_block = True
            continue
        m = _IMPORT_SINGLE_RE.match(line)
        if m:
            specs.append((m.group(1), m.group(2), i))
    return specs


def _strip_comments(lines: list[str]) -> list[str]:
    """Copy of lines with `//` line comments and `/* */` block comments
    blanked, so usage scanning skips commented-out code. String literals are
    NOT tracked (documented limit)."""
    out: list[str] = []
    in_block = False
    for line in lines:
        if in_block:
            end = line.find("*/")
            if end == -1:
                out.append("")
                continue
            line = line[end + 2:]
            in_block = False
        while True:
            start = line.find("/*")
            if start == -1:
                break
            end = line.find("*/", start + 2)
            if end == -1:
                line = line[:start]
                in_block = True
                break
            line = line[:start] + line[end + 2:]
        pos = line.find("//")
        if pos != -1:
            line = line[:pos]
        out.append(line)
    return out


def _resolve_go_symbol(
    graph: RepoGraph, repo: str, pkg_path: str, symbol: str,
) -> tuple[str | None, bool]:
    """Go-semantic resolution: resolved only when a top-level definition of
    the symbol exists in the imported package itself."""
    for d in graph.defs.get((repo, symbol), []):
        if d.module == pkg_path:
            return d.kind, True
    return None, False


def build_graph_go(repos: dict[str, Path]) -> RepoGraph:
    """Two-pass build mirroring kg_graph.build_graph: (1) module/package/def
    discovery from go.mod + top-level decls, (2) import and usage edges."""
    if not repos:
        raise ValueError("repos must be a non-empty {name: root_path} mapping")

    packages: dict[str, str] = {}
    modules: dict[str, set[str]] = {r: set() for r in repos}
    defs: dict[tuple[str, str], list[SymbolDef]] = {}
    graph = RepoGraph(
        repos=dict(repos), packages=packages, modules=modules,
        package_modules=set(), defs=defs,
    )

    module_dirs_by_repo: dict[str, list[tuple[str, Path]]] = {}
    for repo_name, root in repos.items():
        root = Path(root)
        module_dirs_by_repo[repo_name] = _discover_go_modules(root)
        for mod_path, _ in module_dirs_by_repo[repo_name]:
            if mod_path in packages and packages[mod_path] != repo_name:
                raise ValueError(
                    f"module path collision: '{mod_path}' in both "
                    f"'{packages[mod_path]}' and '{repo_name}'"
                )
            packages[mod_path] = repo_name

    # Pass 1: packages (import paths), representative files, symbol defs.
    sources: list[tuple[str, str, str, list[str]]] = []  # repo, pkg, rel, lines
    for repo_name, root in repos.items():
        root = Path(root)
        for go_file in _iter_go_files(root):
            pkg_path = _package_import_path(
                go_file.parent, module_dirs_by_repo[repo_name])
            if pkg_path is None:
                continue
            rel_file = go_file.relative_to(root).as_posix()
            lines = go_file.read_text(
                encoding="utf-8", errors="replace").splitlines()
            modules[repo_name].add(pkg_path)
            graph.module_files.setdefault((repo_name, pkg_path), rel_file)
            sources.append((repo_name, pkg_path, rel_file, lines))
            for i, line in enumerate(lines, start=1):
                m = _FUNC_RE.match(line) or _TYPE_RE.match(line)
                if m:
                    kind = "function" if line.startswith("func") else "class"
                    defs.setdefault((repo_name, m.group(1)), []).append(
                        SymbolDef(repo=repo_name, module=pkg_path,
                                  name=m.group(1), kind=kind,
                                  file=rel_file, line=i))

    # Pass 2: import edges + alias-aware usage edges.
    for repo_name, pkg_path, rel_file, lines in sources:
        bindings: dict[str, str] = {}  # local name -> import path
        for alias, import_path, lineno in _parse_imports(lines):
            dst_repo = _repo_for_import_path(packages, import_path)
            graph.edges.append(ImportEdge(
                src_repo=repo_name, src_module=pkg_path, dst_repo=dst_repo,
                dst_module=import_path, dst_symbol=None, dst_kind=None,
                resolved=dst_repo is not None,
                evidence=Evidence(repo_name, rel_file, lineno,
                                  lines[lineno - 1].strip()[:160]),
            ))
            if alias in ("_", "."):
                continue
            if dst_repo is not None:
                bindings[alias or _binding_name(import_path)] = import_path
        graph.edges.extend(_usage_edges_go(
            graph, repo_name, pkg_path, rel_file, lines, bindings))
    return graph


def _usage_edges_go(
    graph: RepoGraph, repo_name: str, pkg_path: str, rel_file: str,
    lines: list[str], bindings: dict[str, str],
) -> list[ImportEdge]:
    """`name.Symbol` usage edges for bound imports that map to a known repo.
    Only exported symbols (leading uppercase) can be referenced cross-package
    in Go. Deduplicated per (import path, symbol), first line wins."""
    if not bindings:
        return []
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(n) for n in sorted(bindings)) + r")"
        r"\.([A-Z]\w*)"
    )
    best: dict[tuple[str, str], int] = {}
    for i, line in enumerate(_strip_comments(lines), start=1):
        for m in pattern.finditer(line):
            key = (bindings[m.group(1)], m.group(2))
            if key not in best or i < best[key]:
                best[key] = i
    edges: list[ImportEdge] = []
    for (import_path, symbol), lineno in sorted(best.items(), key=lambda kv: kv[1]):
        dst_repo = _repo_for_import_path(graph.packages, import_path)
        assert dst_repo is not None  # filtered when building bindings
        kind, resolved = _resolve_go_symbol(graph, dst_repo, import_path, symbol)
        edges.append(ImportEdge(
            src_repo=repo_name, src_module=pkg_path, dst_repo=dst_repo,
            dst_module=import_path, dst_symbol=symbol, dst_kind=kind,
            resolved=resolved,
            evidence=Evidence(repo_name, rel_file, lineno,
                              lines[lineno - 1].strip()[:160]),
            edge_kind="usage",
        ))
    return edges
