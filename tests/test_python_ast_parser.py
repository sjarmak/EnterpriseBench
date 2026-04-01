"""
Tests for Python AST parser — import resolution and symbol extraction.

Uses inline Python source strings as fixtures (no external files needed).
"""

from __future__ import annotations

import pytest

from eb_verify.parsers.python_ast import (
    ImportInfo,
    Reference,
    SymbolInfo,
    build_import_graph,
    extract_imports,
    extract_symbols,
    find_symbol_references,
    verify_import_chain,
)

# ---------------------------------------------------------------------------
# extract_imports
# ---------------------------------------------------------------------------


class TestExtractImports:
    def test_simple_import(self) -> None:
        source = "import os"
        result = extract_imports(source)
        assert len(result) == 1
        assert result[0] == ImportInfo(module="os", name=None, alias=None, line=1)

    def test_import_alias(self) -> None:
        source = "import numpy as np"
        result = extract_imports(source)
        assert len(result) == 1
        assert result[0] == ImportInfo(module="numpy", name=None, alias="np", line=1)

    def test_from_import(self) -> None:
        source = "from os.path import join"
        result = extract_imports(source)
        assert len(result) == 1
        assert result[0] == ImportInfo(
            module="os.path", name="join", alias=None, line=1
        )

    def test_from_import_alias(self) -> None:
        source = "from collections import OrderedDict as OD"
        result = extract_imports(source)
        assert len(result) == 1
        assert result[0] == ImportInfo(
            module="collections", name="OrderedDict", alias="OD", line=1
        )

    def test_from_import_multiple_names(self) -> None:
        source = "from os.path import join, exists, isfile"
        result = extract_imports(source)
        assert len(result) == 3
        names = {r.name for r in result}
        assert names == {"join", "exists", "isfile"}
        # All share same module and line
        assert all(r.module == "os.path" for r in result)
        assert all(r.line == 1 for r in result)

    def test_relative_import(self) -> None:
        source = "from . import utils"
        result = extract_imports(source)
        assert len(result) == 1
        assert result[0].module == ""
        assert result[0].name == "utils"
        assert result[0].level == 1

    def test_relative_import_with_module(self) -> None:
        source = "from ..models import User"
        result = extract_imports(source)
        assert len(result) == 1
        assert result[0].module == "models"
        assert result[0].name == "User"
        assert result[0].level == 2

    def test_star_import(self) -> None:
        source = "from os.path import *"
        result = extract_imports(source)
        assert len(result) == 1
        assert result[0].name == "*"
        assert result[0].module == "os.path"

    def test_multiple_imports(self) -> None:
        source = """\
import os
import sys
from pathlib import Path
"""
        result = extract_imports(source)
        assert len(result) == 3

    def test_multiline_import(self) -> None:
        source = """\
from os.path import (
    join,
    exists,
)
"""
        result = extract_imports(source)
        assert len(result) == 2

    def test_empty_source(self) -> None:
        assert extract_imports("") == []

    def test_no_imports(self) -> None:
        source = "x = 1\nprint(x)"
        assert extract_imports(source) == []

    def test_syntax_error_returns_empty(self) -> None:
        source = "def broken(:\n  pass"
        assert extract_imports(source) == []


# ---------------------------------------------------------------------------
# extract_symbols
# ---------------------------------------------------------------------------


class TestExtractSymbols:
    def test_function_def(self) -> None:
        source = """\
def hello():
    pass
"""
        result = extract_symbols(source)
        assert len(result) == 1
        assert result[0] == SymbolInfo(name="hello", kind="function", line=1)

    def test_async_function(self) -> None:
        source = """\
async def fetch():
    pass
"""
        result = extract_symbols(source)
        assert len(result) == 1
        assert result[0].name == "fetch"
        assert result[0].kind == "function"

    def test_class_def(self) -> None:
        source = """\
class MyClass:
    pass
"""
        result = extract_symbols(source)
        assert len(result) == 1
        assert result[0] == SymbolInfo(name="MyClass", kind="class", line=1)

    def test_class_with_methods(self) -> None:
        source = """\
class MyClass:
    def method_a(self):
        pass
    def method_b(self):
        pass
"""
        result = extract_symbols(source)
        names = {s.name for s in result}
        # Should include the class and its methods
        assert "MyClass" in names
        assert "MyClass.method_a" in names
        assert "MyClass.method_b" in names

    def test_module_level_variable(self) -> None:
        source = """\
VERSION = "1.0.0"
"""
        result = extract_symbols(source)
        assert len(result) == 1
        assert result[0] == SymbolInfo(name="VERSION", kind="variable", line=1)

    def test_multiple_assignment(self) -> None:
        source = """\
X = 1
Y = 2
"""
        result = extract_symbols(source)
        names = {s.name for s in result}
        assert names == {"X", "Y"}

    def test_decorated_function(self) -> None:
        source = """\
@app.route("/")
def index():
    pass
"""
        result = extract_symbols(source)
        assert any(s.name == "index" and s.kind == "function" for s in result)

    def test_nested_class(self) -> None:
        source = """\
class Outer:
    class Inner:
        pass
"""
        result = extract_symbols(source)
        names = {s.name for s in result}
        assert "Outer" in names
        assert "Outer.Inner" in names

    def test_empty_source(self) -> None:
        assert extract_symbols("") == []

    def test_syntax_error_returns_empty(self) -> None:
        assert extract_symbols("def broken(:\n  pass") == []

    def test_tuple_unpack_ignored(self) -> None:
        """Tuple unpacking at module level should not be extracted as symbols."""
        source = "a, b = 1, 2"
        result = extract_symbols(source)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# build_import_graph
# ---------------------------------------------------------------------------


class TestBuildImportGraph:
    def test_simple_graph(self, tmp_path) -> None:
        # a.py imports from b.py
        a_py = tmp_path / "a.py"
        b_py = tmp_path / "b.py"
        a_py.write_text("from b import helper\n")
        b_py.write_text("def helper(): pass\n")

        graph = build_import_graph([str(a_py), str(b_py)])
        assert str(a_py) in graph
        # a.py should list b as a dependency (module name)
        assert any("b" in dep for dep in graph[str(a_py)])

    def test_no_imports(self, tmp_path) -> None:
        a_py = tmp_path / "a.py"
        a_py.write_text("x = 1\n")

        graph = build_import_graph([str(a_py)])
        assert graph[str(a_py)] == []

    def test_multiple_files(self, tmp_path) -> None:
        a_py = tmp_path / "a.py"
        b_py = tmp_path / "b.py"
        c_py = tmp_path / "c.py"
        a_py.write_text("from b import foo\nfrom c import bar\n")
        b_py.write_text("def foo(): pass\n")
        c_py.write_text("def bar(): pass\n")

        graph = build_import_graph([str(a_py), str(b_py), str(c_py)])
        assert len(graph[str(a_py)]) == 2
        assert graph[str(b_py)] == []
        assert graph[str(c_py)] == []

    def test_circular_imports(self, tmp_path) -> None:
        a_py = tmp_path / "a.py"
        b_py = tmp_path / "b.py"
        a_py.write_text("from b import y\n")
        b_py.write_text("from a import x\n")

        # Should not crash on circular imports
        graph = build_import_graph([str(a_py), str(b_py)])
        assert str(a_py) in graph
        assert str(b_py) in graph

    def test_init_py_package(self, tmp_path) -> None:
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        init = pkg / "__init__.py"
        mod = pkg / "core.py"
        init.write_text("from .core import run\n")
        mod.write_text("def run(): pass\n")

        graph = build_import_graph([str(init), str(mod)])
        assert str(init) in graph


# ---------------------------------------------------------------------------
# find_symbol_references
# ---------------------------------------------------------------------------


class TestFindSymbolReferences:
    def test_function_call(self) -> None:
        source = """\
def greet():
    pass

greet()
"""
        refs = find_symbol_references(source, "greet")
        # Should find at least the call site (not the definition)
        assert len(refs) >= 1
        assert any(r.line == 4 for r in refs)

    def test_attribute_access(self) -> None:
        source = """\
app.route("/")
"""
        refs = find_symbol_references(source, "app")
        assert len(refs) >= 1

    def test_no_references(self) -> None:
        source = "x = 1"
        refs = find_symbol_references(source, "nonexistent")
        assert refs == []

    def test_multiple_references(self) -> None:
        source = """\
print(x)
y = x + 1
z = x * 2
"""
        refs = find_symbol_references(source, "x")
        assert len(refs) == 3

    def test_import_reference(self) -> None:
        source = """\
from flask import Flask
app = Flask(__name__)
"""
        refs = find_symbol_references(source, "Flask")
        # Flask used in the assignment line
        assert any(r.line == 2 for r in refs)

    def test_syntax_error_returns_empty(self) -> None:
        assert find_symbol_references("def broken(:", "x") == []


# ---------------------------------------------------------------------------
# verify_import_chain
# ---------------------------------------------------------------------------


class TestVerifyImportChain:
    def test_direct_import(self) -> None:
        """a.py imports helper from b.py — direct chain."""
        files = {
            "b.py": "def helper(): pass",
            "a.py": "from b import helper",
        }
        assert verify_import_chain(files, "a", "helper") is True

    def test_transitive_import(self) -> None:
        """a.py imports from b.py which imports from c.py — transitive chain."""
        files = {
            "c.py": "def deep_func(): pass",
            "b.py": "from c import deep_func",
            "a.py": "from b import deep_func",
        }
        assert verify_import_chain(files, "a", "deep_func") is True

    def test_no_chain(self) -> None:
        """No import chain exists."""
        files = {
            "a.py": "x = 1",
            "b.py": "def helper(): pass",
        }
        assert verify_import_chain(files, "a", "helper") is False

    def test_symbol_defined_locally(self) -> None:
        """Symbol is defined in the start module itself."""
        files = {
            "a.py": "def helper(): pass",
        }
        assert verify_import_chain(files, "a", "helper") is True

    def test_circular_does_not_hang(self) -> None:
        """Circular imports should not cause infinite loop."""
        files = {
            "a.py": "from b import x",
            "b.py": "from a import y\nx = 1",
        }
        assert verify_import_chain(files, "a", "x") is True

    def test_star_import_chain(self) -> None:
        """Star import makes all symbols transitively available."""
        files = {
            "b.py": "SECRET = 42",
            "a.py": "from b import *",
        }
        assert verify_import_chain(files, "a", "SECRET") is True

    def test_missing_module(self) -> None:
        """Start module not in files dict."""
        files = {
            "b.py": "def helper(): pass",
        }
        assert verify_import_chain(files, "a", "helper") is False


# ---------------------------------------------------------------------------
# Edge cases for real-world Python patterns
# ---------------------------------------------------------------------------


class TestRealWorldPatterns:
    def test_flask_blueprint_pattern(self) -> None:
        source = """\
from flask import Blueprint

bp = Blueprint("auth", __name__, url_prefix="/auth")

@bp.route("/login")
def login():
    return "login"
"""
        imports = extract_imports(source)
        assert any(i.name == "Blueprint" and i.module == "flask" for i in imports)

        symbols = extract_symbols(source)
        names = {s.name for s in symbols}
        assert "bp" in names
        assert "login" in names

    def test_click_decorator_pattern(self) -> None:
        source = """\
import click

@click.command()
@click.option("--name", help="Your name")
def hello(name):
    click.echo(f"Hello {name}")
"""
        imports = extract_imports(source)
        assert any(i.module == "click" for i in imports)

        symbols = extract_symbols(source)
        assert any(s.name == "hello" for s in symbols)

    def test_django_model_pattern(self) -> None:
        source = """\
from django.db import models

class Article(models.Model):
    title = models.CharField(max_length=200)
    body = models.TextField()

    class Meta:
        ordering = ["-created"]
"""
        symbols = extract_symbols(source)
        names = {s.name for s in symbols}
        assert "Article" in names
        assert "Article.Meta" in names

    def test_dunder_all_export(self) -> None:
        source = """\
__all__ = ["public_func", "PublicClass"]

def public_func():
    pass

def _private_func():
    pass

class PublicClass:
    pass
"""
        symbols = extract_symbols(source)
        names = {s.name for s in symbols}
        assert "__all__" in names
        assert "public_func" in names
        assert "_private_func" in names
        assert "PublicClass" in names

    def test_conditional_import(self) -> None:
        """Conditional imports (TYPE_CHECKING) should still be extracted."""
        source = """\
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Flask
"""
        imports = extract_imports(source)
        # The parser extracts all imports regardless of conditional context
        modules = {i.module for i in imports}
        assert "__future__" in modules
        assert "typing" in modules
        # Conditional import inside if block — ast sees it
        assert "flask" in modules

    def test_try_except_import(self) -> None:
        """Try/except imports (compatibility) should be extracted."""
        source = """\
try:
    import ujson as json
except ImportError:
    import json
"""
        imports = extract_imports(source)
        assert len(imports) == 2
        modules = {i.module for i in imports}
        assert "ujson" in modules
        assert "json" in modules
