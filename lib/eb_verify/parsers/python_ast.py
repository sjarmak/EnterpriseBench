"""
Python AST parser — import resolution and symbol extraction using stdlib ast.

Provides deterministic ground truth verification for Python-based benchmark tasks.
"""

from __future__ import annotations

import ast
from collections import deque
from typing import Optional

from eb_verify.parsers.base import ImportInfo, Reference, SymbolInfo


def extract_imports(source: str) -> list[ImportInfo]:
    """Parse all import statements from Python source code.

    Handles: import X, import X as Y, from X import Y, from X import *,
    relative imports (from . import Z, from ..pkg import W).

    Returns empty list on syntax errors.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    results: list[ImportInfo] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                results.append(
                    ImportInfo(
                        module=alias.name,
                        name=None,
                        alias=alias.asname,
                        line=node.lineno,
                        level=0,
                    )
                )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            level = node.level or 0
            for alias in node.names:
                results.append(
                    ImportInfo(
                        module=module,
                        name=alias.name,
                        alias=alias.asname,
                        line=node.lineno,
                        level=level,
                    )
                )

    return results


def extract_symbols(source: str) -> list[SymbolInfo]:
    """Extract top-level and class-level symbol definitions.

    Extracts:
    - Functions (def, async def) at module level
    - Classes at module level, and nested classes
    - Methods within classes (as ClassName.method_name)
    - Module-level variable assignments (simple Name targets only)

    Returns empty list on syntax errors.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    results: list[SymbolInfo] = []

    def _visit_class(node: ast.ClassDef, prefix: str) -> None:
        """Recursively visit class body for methods and nested classes."""
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                results.append(
                    SymbolInfo(
                        name=f"{prefix}.{item.name}",
                        kind="method",
                        line=item.lineno,
                    )
                )
            elif isinstance(item, ast.ClassDef):
                qualified = f"{prefix}.{item.name}"
                results.append(
                    SymbolInfo(name=qualified, kind="class", line=item.lineno)
                )
                _visit_class(item, qualified)

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            results.append(
                SymbolInfo(name=node.name, kind="function", line=node.lineno)
            )
        elif isinstance(node, ast.ClassDef):
            results.append(SymbolInfo(name=node.name, kind="class", line=node.lineno))
            _visit_class(node, node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    results.append(
                        SymbolInfo(name=target.id, kind="variable", line=node.lineno)
                    )

    return results


def find_symbol_references(source: str, symbol_name: str) -> list[Reference]:
    """Find all references (usages) of a symbol in source code.

    Walks the AST looking for Name nodes matching symbol_name.
    Excludes the definition site (function/class def names).

    Returns empty list on syntax errors.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    # Collect definition line numbers to exclude
    def_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == symbol_name:
                def_lines.add(node.lineno)

    refs: list[Reference] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == symbol_name:
            if node.lineno not in def_lines:
                refs.append(
                    Reference(
                        name=symbol_name,
                        line=node.lineno,
                        col=node.col_offset,
                    )
                )

    return refs


def build_import_graph(file_paths: list[str]) -> dict[str, list[str]]:
    """Build an import dependency graph across multiple Python files.

    Args:
        file_paths: Absolute paths to Python source files.

    Returns:
        Dict mapping each file path to a list of module names it imports.
    """
    graph: dict[str, list[str]] = {}

    for path in file_paths:
        try:
            with open(path) as f:
                source = f.read()
        except OSError:
            graph[path] = []
            continue

        imports = extract_imports(source)
        modules: list[str] = []
        for imp in imports:
            if imp.name is not None and imp.module:
                modules.append(imp.module)
            elif imp.name is not None and not imp.module:
                # Relative import like "from . import utils"
                modules.append(imp.name)
            elif imp.module:
                modules.append(imp.module)

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for m in modules:
            if m not in seen:
                seen.add(m)
                unique.append(m)

        graph[path] = unique

    return graph


def _module_name_from_path(path: str) -> str:
    """Extract a simple module name from a file path.

    'foo/bar/baz.py' -> 'baz'
    'pkg/__init__.py' -> 'pkg'
    """
    import os

    base = os.path.basename(path)
    if base == "__init__.py":
        return os.path.basename(os.path.dirname(path))
    return os.path.splitext(base)[0]


def verify_import_chain(
    source_files: dict[str, str],
    start_module: str,
    target_symbol: str,
) -> bool:
    """Verify that an import chain exists from start_module to target_symbol.

    Args:
        source_files: Dict mapping module filenames (e.g. 'a.py') to source code.
        start_module: Module name to start from (without .py).
        target_symbol: Symbol name to find.

    Returns:
        True if the start module can reach the target symbol through imports.
    """
    # Build module name -> source mapping
    modules: dict[str, str] = {}
    for filename, source in source_files.items():
        mod_name = filename.replace(".py", "")
        modules[mod_name] = source

    if start_module not in modules:
        return False

    # BFS through import chain
    visited: set[str] = set()
    queue: deque[str] = deque([start_module])

    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)

        source = modules.get(current)
        if source is None:
            continue

        # Check if symbol is defined in this module
        symbols = extract_symbols(source)
        symbol_names = {s.name for s in symbols}
        if target_symbol in symbol_names:
            return True

        # Check imports for the symbol or modules to traverse
        imports = extract_imports(source)
        for imp in imports:
            # Direct import of the target symbol
            if imp.name == target_symbol:
                # Check if the source module has it
                imp_module = imp.module if imp.module else imp.name
                if imp_module in modules:
                    queue.append(imp_module)
                else:
                    # External module — assume it provides the symbol
                    return True

            # Star import — need to check the module for the symbol
            if imp.name == "*" and imp.module:
                if imp.module in modules:
                    queue.append(imp.module)

            # Module import — add to traversal
            if imp.module and imp.module in modules and imp.module not in visited:
                queue.append(imp.module)

    return False


class PythonASTParser:
    """Python language parser using stdlib ast module."""

    language = "python"

    def extract_imports(self, source: str) -> list[ImportInfo]:
        return extract_imports(source)

    def extract_symbols(self, source: str) -> list[SymbolInfo]:
        return extract_symbols(source)

    def find_symbol_references(self, source: str, symbol_name: str) -> list[Reference]:
        return find_symbol_references(source, symbol_name)
