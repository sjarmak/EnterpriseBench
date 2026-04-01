"""
Go AST parser — regex-based import resolution and symbol extraction.

Provides deterministic ground truth verification for Go-based benchmark tasks
(Kubernetes, etcd, gRPC-Go, etc.) without requiring the Go toolchain.

All parsing is regex-based — no subprocess calls to `go` are needed.
"""

from __future__ import annotations

import re
from collections import deque
from typing import Optional

from eb_verify.parsers.base import ImportInfo, Reference, SymbolInfo

# ---------------------------------------------------------------------------
# Regex patterns for Go source
# ---------------------------------------------------------------------------

# package <name>
_PACKAGE_RE = re.compile(r"^\s*package\s+(\w+)", re.MULTILINE)

# Single-line import: import "path" or import alias "path"
_SINGLE_IMPORT_RE = re.compile(r'^\s*import\s+(?:(\w+|\.)\s+)?"([^"]+)"', re.MULTILINE)

# Grouped import block: import ( ... )
_GROUPED_IMPORT_RE = re.compile(r"^\s*import\s*\((.*?)\n\)", re.MULTILINE | re.DOTALL)

# Single line within a grouped import block
# Matches: alias "path", . "path", _ "path", "path"
_IMPORT_LINE_RE = re.compile(r'^\s*(?:(\w+|[._])\s+)?"([^"]+)"', re.MULTILINE)

# func Name( or func (receiver) Name(
_FUNC_RE = re.compile(
    r"^func\s+"
    r"(?:\(\s*\w+\s+(\*?\w+(?:\[.*?\])?)\s*\)\s+)?"  # optional receiver
    r"(\w+)"  # function name
    r"\s*(?:\[.*?\])?"  # optional type params
    r"\s*\(",  # opening paren
    re.MULTILINE,
)

# type Name struct {
_TYPE_STRUCT_RE = re.compile(r"^type\s+(\w+)\s+struct\b", re.MULTILINE)

# type Name interface {
_TYPE_INTERFACE_RE = re.compile(r"^type\s+(\w+)\s+interface\b", re.MULTILINE)

# type Name <other> (simple type alias / definition, not struct or interface)
_TYPE_ALIAS_RE = re.compile(r"^type\s+(\w+)\s+(?!struct\b|interface\b)\S", re.MULTILINE)

# var Name ... (single-line)
_VAR_SINGLE_RE = re.compile(r"^var\s+(\w+)\b", re.MULTILINE)

# const Name ... (single-line)
_CONST_SINGLE_RE = re.compile(r"^const\s+(\w+)\b", re.MULTILINE)

# var ( ... ) block — match up to a closing paren at the start of a line
_VAR_BLOCK_RE = re.compile(r"^var\s*\((.*?)\n\)", re.MULTILINE | re.DOTALL)

# const ( ... ) block
_CONST_BLOCK_RE = re.compile(r"^const\s*\((.*?)\n\)", re.MULTILINE | re.DOTALL)

# Identifier at start of a line in a const/var block (with optional type/value)
_BLOCK_ENTRY_RE = re.compile(r"^\s+(\w+)\b", re.MULTILINE)


def is_exported(name: str) -> bool:
    """Check if a Go identifier is exported (starts with uppercase)."""
    if not name:
        return False
    return name[0].isupper()


def extract_package(source: str) -> Optional[str]:
    """Extract the package declaration from Go source."""
    m = _PACKAGE_RE.search(source)
    return m.group(1) if m else None


def extract_imports(source: str) -> list[ImportInfo]:
    """Parse all import declarations from Go source code.

    Handles single imports, grouped imports, aliases, dot imports,
    and blank (_) imports. Ignores commented-out lines.
    """
    results: list[ImportInfo] = []

    # Single-line imports
    for m in _SINGLE_IMPORT_RE.finditer(source):
        alias = m.group(1)  # may be None
        path = m.group(2)
        results.append(ImportInfo(module=path, alias=alias))

    # Grouped import blocks
    for block_match in _GROUPED_IMPORT_RE.finditer(source):
        block = block_match.group(1)
        for line in block.splitlines():
            stripped = line.strip()
            # Skip empty lines and full-line comments
            if not stripped or stripped.startswith("//"):
                continue
            line_m = _IMPORT_LINE_RE.match(stripped)
            if line_m:
                alias = line_m.group(1)  # may be None
                path = line_m.group(2)
                results.append(ImportInfo(module=path, alias=alias))

    return results


def _line_number(source: str, pos: int) -> int:
    """Convert a character position to a 1-based line number."""
    return source[:pos].count("\n") + 1


def extract_symbols(source: str) -> list[SymbolInfo]:
    """Extract all top-level symbol declarations from Go source code.

    Extracts: functions, methods (with receivers), struct types, interface types,
    type aliases, var declarations, const declarations (including iota blocks).
    """
    results: list[SymbolInfo] = []

    # Functions and methods
    for m in _FUNC_RE.finditer(source):
        receiver = m.group(1)  # None for plain functions
        name = m.group(2)
        kind = "method" if receiver else "function"
        results.append(
            SymbolInfo(name=name, kind=kind, line=_line_number(source, m.start()))
        )

    # Struct types
    for m in _TYPE_STRUCT_RE.finditer(source):
        results.append(
            SymbolInfo(
                name=m.group(1), kind="struct", line=_line_number(source, m.start())
            )
        )

    # Interface types
    for m in _TYPE_INTERFACE_RE.finditer(source):
        results.append(
            SymbolInfo(
                name=m.group(1), kind="interface", line=_line_number(source, m.start())
            )
        )

    # Type aliases (not struct/interface)
    for m in _TYPE_ALIAS_RE.finditer(source):
        results.append(
            SymbolInfo(
                name=m.group(1), kind="type", line=_line_number(source, m.start())
            )
        )

    # Single-line var (exclude "var (")
    for m in _VAR_SINGLE_RE.finditer(source):
        # Make sure this isn't the start of a var block
        rest = source[m.end() :]
        if not rest.lstrip().startswith("(") and m.group(1) != "(":
            results.append(
                SymbolInfo(
                    name=m.group(1),
                    kind="variable",
                    line=_line_number(source, m.start()),
                )
            )

    # Single-line const (exclude "const (")
    for m in _CONST_SINGLE_RE.finditer(source):
        rest = source[m.end() :]
        if not rest.lstrip().startswith("(") and m.group(1) != "(":
            results.append(
                SymbolInfo(
                    name=m.group(1),
                    kind="constant",
                    line=_line_number(source, m.start()),
                )
            )

    # Var blocks
    for block_match in _VAR_BLOCK_RE.finditer(source):
        block = block_match.group(1)
        block_start_line = _line_number(source, block_match.start())
        for entry_m in _BLOCK_ENTRY_RE.finditer(block):
            name = entry_m.group(1)
            # Skip Go keywords and comments
            if name in ("_", "//"):
                continue
            entry_line = block_start_line + block[: entry_m.start()].count("\n") + 1
            results.append(SymbolInfo(name=name, kind="variable", line=entry_line))

    # Const blocks
    for block_match in _CONST_BLOCK_RE.finditer(source):
        block = block_match.group(1)
        block_start_line = _line_number(source, block_match.start())
        for entry_m in _BLOCK_ENTRY_RE.finditer(block):
            name = entry_m.group(1)
            if name in ("_", "//"):
                continue
            entry_line = block_start_line + block[: entry_m.start()].count("\n") + 1
            results.append(SymbolInfo(name=name, kind="constant", line=entry_line))

    return results


def find_symbol_references(source: str, symbol_name: str) -> list[Reference]:
    """Find all references to a named symbol in Go source code.

    Uses word-boundary matching to avoid false positives from substrings.
    """
    pattern = re.compile(r"\b" + re.escape(symbol_name) + r"\b")
    refs: list[Reference] = []

    for line_idx, line in enumerate(source.splitlines(), start=1):
        # Skip comment-only lines
        stripped = line.lstrip()
        if stripped.startswith("//"):
            continue
        for m in pattern.finditer(line):
            refs.append(Reference(name=symbol_name, line=line_idx, col=m.start()))

    return refs


def build_import_graph(source_files: dict[str, str]) -> dict[str, list[str]]:
    """Build an import dependency graph across multiple Go files.

    Args:
        source_files: Dict mapping file paths to Go source code.

    Returns:
        Dict mapping each file path to a list of import module paths.
    """
    graph: dict[str, list[str]] = {}

    for file_path, source in source_files.items():
        imports = extract_imports(source)
        modules: list[str] = []
        seen: set[str] = set()
        for imp in imports:
            if imp.module not in seen:
                seen.add(imp.module)
                modules.append(imp.module)
        graph[file_path] = modules

    return graph


def verify_import_chain(
    source_files: dict[str, str],
    start_pkg: str,
    target_symbol: str,
) -> bool:
    """Verify that an import chain exists from start_pkg to target_symbol.

    Args:
        source_files: Dict mapping file paths to Go source code.
        start_pkg: Package name to start from.
        target_symbol: Symbol name to find.

    Returns:
        True if the start package can reach the target symbol through imports.
    """
    # Build package name -> list of (file_path, source) mapping
    pkg_files: dict[str, list[tuple[str, str]]] = {}
    for file_path, source in source_files.items():
        pkg = extract_package(source)
        if pkg:
            pkg_files.setdefault(pkg, []).append((file_path, source))

    if start_pkg not in pkg_files:
        return False

    # BFS through import chain
    visited: set[str] = set()
    queue: deque[str] = deque([start_pkg])

    while queue:
        current_pkg = queue.popleft()
        if current_pkg in visited:
            continue
        visited.add(current_pkg)

        files = pkg_files.get(current_pkg, [])
        for _fp, source in files:
            # Check if symbol is defined in this package's files
            symbols = extract_symbols(source)
            if any(s.name == target_symbol for s in symbols):
                return True

            # Add imported packages to traversal
            imports = extract_imports(source)
            for imp in imports:
                # Resolve import path to package name
                # The last segment of the import path is typically the package name
                imp_pkg = (
                    imp.module.rsplit("/", 1)[-1] if "/" in imp.module else imp.module
                )
                if imp_pkg not in visited:
                    queue.append(imp_pkg)

    return False


class GoParser:
    """Go language parser using regex-based extraction.

    Implements the LanguageParser protocol for integration with
    the eb_verify parser registry.
    """

    language = "go"

    def extract_imports(self, source: str) -> list[ImportInfo]:
        return extract_imports(source)

    def extract_symbols(self, source: str) -> list[SymbolInfo]:
        return extract_symbols(source)

    def find_symbol_references(self, source: str, symbol_name: str) -> list[Reference]:
        return find_symbol_references(source, symbol_name)
