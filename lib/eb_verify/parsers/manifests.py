"""
Manifest parsers for npm, Go, and Python dependency files.

All parsers use only Python stdlib (json, configparser, tomllib).
No external dependencies required.
"""

from __future__ import annotations

import configparser
import io
import json
import re
import tomllib
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Common types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Dependency:
    """A single dependency with name, version constraint, and optional flag."""

    name: str
    version_constraint: str = ""
    optional: bool = False


@dataclass
class ManifestInfo:
    """Parsed manifest metadata."""

    name: str = ""
    version: str = ""
    dependencies: List[Dependency] = field(default_factory=list)
    dev_dependencies: List[Dependency] = field(default_factory=list)
    peer_dependencies: List[Dependency] = field(default_factory=list)
    extra: Dict = field(default_factory=dict)


class DependencyGraph:
    """Directed graph with version-constraint-annotated edges."""

    def __init__(self) -> None:
        self._adj: Dict[str, List[Tuple[str, str]]] = {}

    def add_edge(self, source: str, target: str, constraint: str = "") -> None:
        self._adj.setdefault(source, [])
        self._adj.setdefault(target, [])
        self._adj[source].append((target, constraint))

    def nodes(self) -> Set[str]:
        return set(self._adj.keys())

    def edges_from(self, node: str) -> List[Tuple[str, str]]:
        return list(self._adj.get(node, []))


def is_transitive_dep(graph: DependencyGraph, source: str, target: str) -> bool:
    """Check if target is reachable from source via BFS."""
    if source == target:
        return True
    visited: Set[str] = set()
    queue: deque[str] = deque([source])
    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        for neighbor, _ in graph.edges_from(current):
            if neighbor == target:
                return True
            if neighbor not in visited:
                queue.append(neighbor)
    return False


def find_dep_path(graph: DependencyGraph, source: str, target: str) -> List[str]:
    """Return the shortest dependency chain from source to target, or [] if none."""
    if source == target:
        return [source]
    visited: Set[str] = set()
    queue: deque[List[str]] = deque([[source]])
    while queue:
        path = queue.popleft()
        current = path[-1]
        if current in visited:
            continue
        visited.add(current)
        for neighbor, _ in graph.edges_from(current):
            new_path = path + [neighbor]
            if neighbor == target:
                return new_path
            if neighbor not in visited:
                queue.append(new_path)
    return []


# ---------------------------------------------------------------------------
# npm parsers
# ---------------------------------------------------------------------------


def _parse_dep_dict(deps: Dict[str, str], optional: bool = False) -> List[Dependency]:
    return [
        Dependency(name=name, version_constraint=ver, optional=optional)
        for name, ver in deps.items()
    ]


def parse_package_json(content: str) -> ManifestInfo:
    """Parse a package.json string into ManifestInfo."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc

    return ManifestInfo(
        name=data.get("name", ""),
        version=data.get("version", ""),
        dependencies=_parse_dep_dict(data.get("dependencies", {})),
        dev_dependencies=_parse_dep_dict(data.get("devDependencies", {})),
        peer_dependencies=_parse_dep_dict(data.get("peerDependencies", {})),
    )


def parse_package_lock(content: str) -> Dict[str, str]:
    """Parse package-lock.json and return {package_name: resolved_version}."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc

    result: Dict[str, str] = {}

    # lockfileVersion 2/3 uses "packages" with node_modules/ paths
    packages = data.get("packages", {})
    for pkg_path, pkg_info in packages.items():
        if not pkg_path:
            continue  # root package entry
        # Extract package name from path like "node_modules/lodash"
        # or "node_modules/@scope/pkg"
        parts = pkg_path.split("node_modules/")
        if len(parts) >= 2:
            pkg_name = parts[-1]
            version = pkg_info.get("version", "")
            if pkg_name and version:
                result[pkg_name] = version

    # lockfileVersion 1 uses "dependencies"
    lock_deps = data.get("dependencies", {})
    if isinstance(lock_deps, dict) and not packages:
        for name, info in lock_deps.items():
            if isinstance(info, dict):
                version = info.get("version", "")
                if version:
                    result[name] = version

    return result


def build_npm_dep_graph(package_jsons: Dict[str, str]) -> DependencyGraph:
    """Build a dependency graph from a mapping of {label: package.json_content}.

    Edges are added for both dependencies and devDependencies.
    Package names are used as node IDs.
    """
    graph = DependencyGraph()
    parsed: Dict[str, ManifestInfo] = {}

    for label, content in package_jsons.items():
        info = parse_package_json(content)
        parsed[label] = info

    # Map package names to labels for resolution
    name_to_label: Dict[str, str] = {}
    for label, info in parsed.items():
        name = info.name or label
        name_to_label[name] = label

    for label, info in parsed.items():
        source = info.name or label
        all_deps = info.dependencies + info.dev_dependencies + info.peer_dependencies
        for dep in all_deps:
            graph.add_edge(source, dep.name, dep.version_constraint)

    return graph


# ---------------------------------------------------------------------------
# Go module parsers
# ---------------------------------------------------------------------------

# Regex patterns for go.mod parsing
_GO_MODULE_RE = re.compile(r"^module\s+(\S+)", re.MULTILINE)
_GO_VERSION_RE = re.compile(r"^go\s+(\S+)", re.MULTILINE)
_GO_SINGLE_REQUIRE_RE = re.compile(
    r"^require\s+(\S+)\s+(\S+)(?:\s+//\s*indirect)?$", re.MULTILINE
)
_GO_REPLACE_SINGLE_RE = re.compile(r"^replace\s+(\S+)\s+=>\s+(.+)$", re.MULTILINE)
_GO_EXCLUDE_SINGLE_RE = re.compile(r"^exclude\s+(\S+\s+\S+)", re.MULTILINE)


def _parse_require_block(block: str) -> List[Dependency]:
    """Parse entries inside a require ( ... ) block."""
    deps: List[Dependency] = []
    for line in block.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        indirect = "// indirect" in line
        # Remove inline comments
        line = line.split("//")[0].strip()
        parts = line.split()
        if len(parts) >= 2:
            deps.append(
                Dependency(
                    name=parts[0],
                    version_constraint=parts[1],
                    optional=indirect,
                )
            )
    return deps


def _extract_blocks(content: str, directive: str) -> List[str]:
    """Extract all ( ... ) blocks for a given directive (require, replace, exclude)."""
    blocks: List[str] = []
    pattern = re.compile(
        rf"^{directive}\s*\(\s*$(.+?)^\s*\)",
        re.MULTILINE | re.DOTALL,
    )
    for match in pattern.finditer(content):
        blocks.append(match.group(1))
    return blocks


def parse_go_mod(content: str) -> ManifestInfo:
    """Parse a go.mod file into ManifestInfo."""
    # Module path
    m = _GO_MODULE_RE.search(content)
    name = m.group(1) if m else ""

    # Go version
    m = _GO_VERSION_RE.search(content)
    version = m.group(1) if m else ""

    # Requirements
    deps: List[Dependency] = []

    # Block requires: require ( ... )
    for block in _extract_blocks(content, "require"):
        deps.extend(_parse_require_block(block))

    # Single-line requires: require golang.org/x/net v0.5.0
    for match in _GO_SINGLE_REQUIRE_RE.finditer(content):
        mod_path = match.group(1)
        mod_ver = match.group(2)
        indirect = "// indirect" in match.group(0)
        # Avoid duplicates from block parsing
        if not any(d.name == mod_path for d in deps):
            deps.append(
                Dependency(
                    name=mod_path,
                    version_constraint=mod_ver,
                    optional=indirect,
                )
            )

    # Replace directives
    replaces: Dict[str, str] = {}
    for block in _extract_blocks(content, "replace"):
        for line in block.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            parts = line.split("=>")
            if len(parts) == 2:
                src = parts[0].strip().split()[0]
                dst = parts[1].strip()
                replaces[src] = dst

    for match in _GO_REPLACE_SINGLE_RE.finditer(content):
        src = match.group(1).strip()
        dst = match.group(2).strip()
        replaces[src] = dst

    # Exclude directives
    excludes: List[str] = []
    for block in _extract_blocks(content, "exclude"):
        for line in block.strip().splitlines():
            line = line.strip()
            if line and not line.startswith("//"):
                excludes.append(line)

    for match in _GO_EXCLUDE_SINGLE_RE.finditer(content):
        excludes.append(match.group(1).strip())

    extra: Dict = {}
    if replaces:
        extra["replace"] = replaces
    if excludes:
        extra["exclude"] = excludes

    return ManifestInfo(
        name=name,
        version=version,
        dependencies=deps,
        extra=extra,
    )


def parse_go_sum(content: str) -> Dict[str, Dict[str, str]]:
    """Parse go.sum and return {module: {version, hash}}.

    Only captures the first version seen for each module.
    """
    result: Dict[str, Dict[str, str]] = {}
    for line in content.strip().splitlines():
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) >= 3:
            mod = parts[0]
            ver = parts[1].replace("/go.mod", "")
            h = parts[2]
            if mod not in result:
                result[mod] = {"version": ver, "hash": h}
    return result


def build_go_dep_graph(go_mods: Dict[str, str]) -> DependencyGraph:
    """Build a dependency graph from a mapping of {label: go.mod_content}.

    Module paths (from 'module' directive) are used as node IDs.
    """
    graph = DependencyGraph()
    parsed: Dict[str, ManifestInfo] = {}

    for label, content in go_mods.items():
        info = parse_go_mod(content)
        parsed[label] = info

    for label, info in parsed.items():
        source = info.name or label
        for dep in info.dependencies:
            graph.add_edge(source, dep.name, dep.version_constraint)

    return graph


# ---------------------------------------------------------------------------
# Python parsers
# ---------------------------------------------------------------------------

# Pattern for a Python dependency specifier: name[extras]>=version,<version
_PY_DEP_RE = re.compile(r"^([A-Za-z0-9][\w.\-]*(?:\[[^\]]+\])?)\s*(.*)")


def _parse_python_dep_line(line: str) -> Optional[Dependency]:
    """Parse a single Python dependency line into a Dependency, or None."""
    line = line.strip()
    if (
        not line
        or line.startswith("#")
        or line.startswith("-")
        or line.startswith("--")
    ):
        return None

    # Strip inline comments
    if " #" in line:
        line = line[: line.index(" #")].strip()

    # Strip line continuations and hash options
    line = line.split("\\")[0].strip()
    line = line.split("--hash=")[0].strip()

    match = _PY_DEP_RE.match(line)
    if not match:
        return None

    name = match.group(1)
    constraint = match.group(2).strip()
    # Clean trailing semicolons (environment markers) — keep the constraint part
    if ";" in constraint:
        constraint = constraint.split(";")[0].strip()

    return Dependency(name=name, version_constraint=constraint)


def parse_requirements_txt(content: str) -> List[Dependency]:
    """Parse a requirements.txt file into a list of Dependencies."""
    deps: List[Dependency] = []
    for line in content.splitlines():
        dep = _parse_python_dep_line(line)
        if dep is not None:
            deps.append(dep)
    return deps


def parse_setup_cfg(content: str) -> ManifestInfo:
    """Parse a setup.cfg file into ManifestInfo."""
    parser = configparser.ConfigParser()
    parser.read_string(content)

    name = parser.get("metadata", "name", fallback="")
    version = parser.get("metadata", "version", fallback="")

    # install_requires
    deps: List[Dependency] = []
    install_requires = parser.get("options", "install_requires", fallback="")
    for line in install_requires.strip().splitlines():
        dep = _parse_python_dep_line(line)
        if dep is not None:
            deps.append(dep)

    # extras_require
    extras: Dict[str, List[str]] = {}
    if parser.has_section("options.extras_require"):
        for key in parser.options("options.extras_require"):
            raw = parser.get("options.extras_require", key)
            extras[key] = [
                line.strip() for line in raw.strip().splitlines() if line.strip()
            ]

    extra: Dict = {}
    if extras:
        extra["extras_require"] = extras

    return ManifestInfo(
        name=name,
        version=version,
        dependencies=deps,
        extra=extra,
    )


def parse_pyproject_toml(content: str) -> ManifestInfo:
    """Parse a pyproject.toml file into ManifestInfo."""
    data = tomllib.loads(content)

    project = data.get("project", {})
    name = project.get("name", "")
    version = project.get("version", "")

    # dependencies
    deps: List[Dependency] = []
    for raw in project.get("dependencies", []):
        dep = _parse_python_dep_line(raw)
        if dep is not None:
            deps.append(dep)

    # optional-dependencies
    opt_deps = project.get("optional-dependencies", {})
    extra: Dict = {}
    if opt_deps:
        extra["optional_dependencies"] = {
            group: list(items) for group, items in opt_deps.items()
        }

    return ManifestInfo(
        name=name,
        version=version,
        dependencies=deps,
        extra=extra,
    )


def build_python_dep_graph(manifests: Dict[str, str]) -> DependencyGraph:
    """Build a dependency graph from a mapping of {label: pyproject.toml_content}.

    Attempts pyproject.toml parsing first, falls back to requirements.txt style.
    Package names are normalized for matching.
    """
    graph = DependencyGraph()
    parsed: Dict[str, ManifestInfo] = {}

    for label, content in manifests.items():
        # Try pyproject.toml format first
        try:
            info = parse_pyproject_toml(content)
            if info.name:
                parsed[label] = info
                continue
        except Exception:
            pass

        # Try setup.cfg
        try:
            info = parse_setup_cfg(content)
            if info.name:
                parsed[label] = info
                continue
        except Exception:
            pass

        # Fall back to requirements.txt
        deps = parse_requirements_txt(content)
        parsed[label] = ManifestInfo(name=label, dependencies=deps)

    for label, info in parsed.items():
        source = info.name or label
        for dep in info.dependencies:
            # Normalize: strip extras bracket for graph node matching
            dep_name = dep.name.split("[")[0] if "[" in dep.name else dep.name
            graph.add_edge(source, dep_name, dep.version_constraint)

    return graph
