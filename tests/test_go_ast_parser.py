"""
Tests for Go AST regex-based parser.

Covers: import extraction, symbol extraction, package declarations,
exported/unexported detection, import graph building, import chain verification,
and symbol reference finding.
"""

from __future__ import annotations

import pytest

from eb_verify.parsers.base import ImportInfo, Reference, SymbolInfo
from eb_verify.parsers.go_ast import (
    GoParser,
    build_import_graph,
    extract_imports,
    extract_package,
    extract_symbols,
    find_symbol_references,
    is_exported,
    verify_import_chain,
)


@pytest.fixture
def parser() -> GoParser:
    return GoParser()


# ---------------------------------------------------------------------------
# Package extraction
# ---------------------------------------------------------------------------


class TestExtractPackage:
    def test_simple_package(self) -> None:
        src = 'package main\n\nimport "fmt"\n'
        assert extract_package(src) == "main"

    def test_package_with_comment(self) -> None:
        src = "// Package server implements HTTP handlers.\npackage server\n"
        assert extract_package(src) == "server"

    def test_no_package(self) -> None:
        assert extract_package("// just a comment") is None

    def test_package_with_leading_whitespace(self) -> None:
        src = "\n\n  package  utils\n"
        assert extract_package(src) == "utils"


# ---------------------------------------------------------------------------
# Exported detection
# ---------------------------------------------------------------------------


class TestIsExported:
    def test_uppercase_exported(self) -> None:
        assert is_exported("HandleRequest") is True

    def test_lowercase_unexported(self) -> None:
        assert is_exported("handleRequest") is False

    def test_underscore_unexported(self) -> None:
        assert is_exported("_private") is False

    def test_single_char_exported(self) -> None:
        assert is_exported("X") is True

    def test_single_char_unexported(self) -> None:
        assert is_exported("x") is False

    def test_empty_string(self) -> None:
        assert is_exported("") is False


# ---------------------------------------------------------------------------
# Import extraction
# ---------------------------------------------------------------------------


class TestExtractImports:
    def test_single_import(self) -> None:
        src = 'package main\n\nimport "fmt"\n'
        imports = extract_imports(src)
        assert len(imports) == 1
        assert imports[0] == ImportInfo(module="fmt")

    def test_grouped_imports(self) -> None:
        src = '''package main

import (
\t"context"
\t"fmt"
\t"os"
)
'''
        imports = extract_imports(src)
        modules = [i.module for i in imports]
        assert modules == ["context", "fmt", "os"]

    def test_aliased_import(self) -> None:
        src = '''package main

import (
\tpb "google.golang.org/grpc/status"
\t"fmt"
)
'''
        imports = extract_imports(src)
        assert len(imports) == 2
        pb_import = next(i for i in imports if i.alias == "pb")
        assert pb_import.module == "google.golang.org/grpc/status"

    def test_dot_import(self) -> None:
        src = '''package main

import (
\t. "github.com/onsi/gomega"
)
'''
        imports = extract_imports(src)
        assert len(imports) == 1
        assert imports[0].alias == "."
        assert imports[0].module == "github.com/onsi/gomega"

    def test_blank_import(self) -> None:
        src = '''package main

import (
\t_ "net/http/pprof"
\t"fmt"
)
'''
        imports = extract_imports(src)
        assert len(imports) == 2
        blank = next(i for i in imports if i.alias == "_")
        assert blank.module == "net/http/pprof"

    def test_multiple_import_groups(self) -> None:
        src = '''package main

import "fmt"

import (
\t"os"
\t"path"
)
'''
        imports = extract_imports(src)
        modules = [i.module for i in imports]
        assert "fmt" in modules
        assert "os" in modules
        assert "path" in modules

    def test_import_with_inline_comment(self) -> None:
        src = '''package main

import (
\t"fmt" // standard formatting
\t"os"
)
'''
        imports = extract_imports(src)
        modules = [i.module for i in imports]
        assert "fmt" in modules
        assert "os" in modules

    def test_commented_out_import_ignored(self) -> None:
        src = '''package main

import (
\t"fmt"
\t// "unused"
\t"os"
)
'''
        imports = extract_imports(src)
        modules = [i.module for i in imports]
        assert "fmt" in modules
        assert "os" in modules
        assert "unused" not in modules

    def test_empty_import_block(self) -> None:
        src = "package main\n\nimport ()\n"
        imports = extract_imports(src)
        assert imports == []

    def test_no_imports(self) -> None:
        src = "package main\n\nfunc main() {}\n"
        imports = extract_imports(src)
        assert imports == []


# ---------------------------------------------------------------------------
# Symbol extraction
# ---------------------------------------------------------------------------


class TestExtractSymbols:
    def test_exported_function(self) -> None:
        src = '''package main

func HandleRequest(w http.ResponseWriter, r *http.Request) {
}
'''
        symbols = extract_symbols(src)
        funcs = [s for s in symbols if s.kind == "function"]
        assert len(funcs) == 1
        assert funcs[0].name == "HandleRequest"

    def test_unexported_function(self) -> None:
        src = '''package main

func handleRequest(w http.ResponseWriter, r *http.Request) {
}
'''
        symbols = extract_symbols(src)
        funcs = [s for s in symbols if s.kind == "function"]
        assert len(funcs) == 1
        assert funcs[0].name == "handleRequest"

    def test_method_with_pointer_receiver(self) -> None:
        src = '''package main

func (s *Server) Start(addr string) error {
}
'''
        symbols = extract_symbols(src)
        methods = [s for s in symbols if s.kind == "method"]
        assert len(methods) == 1
        assert methods[0].name == "Start"

    def test_method_with_value_receiver(self) -> None:
        src = '''package main

func (p Point) String() string {
}
'''
        symbols = extract_symbols(src)
        methods = [s for s in symbols if s.kind == "method"]
        assert len(methods) == 1
        assert methods[0].name == "String"

    def test_struct_type(self) -> None:
        src = '''package main

type Server struct {
\taddr string
\tport int
}
'''
        symbols = extract_symbols(src)
        structs = [s for s in symbols if s.kind == "struct"]
        assert len(structs) == 1
        assert structs[0].name == "Server"

    def test_interface_type(self) -> None:
        src = '''package main

type Handler interface {
\tServeHTTP(w ResponseWriter, r *Request)
}
'''
        symbols = extract_symbols(src)
        ifaces = [s for s in symbols if s.kind == "interface"]
        assert len(ifaces) == 1
        assert ifaces[0].name == "Handler"

    def test_simple_type_alias(self) -> None:
        src = '''package main

type Duration int64
'''
        symbols = extract_symbols(src)
        types = [s for s in symbols if s.kind == "type"]
        assert len(types) == 1
        assert types[0].name == "Duration"

    def test_var_declaration(self) -> None:
        src = '''package main

var ErrNotFound = errors.New("not found")
'''
        symbols = extract_symbols(src)
        variables = [s for s in symbols if s.kind == "variable"]
        assert len(variables) == 1
        assert variables[0].name == "ErrNotFound"

    def test_const_declaration(self) -> None:
        src = '''package main

const MaxRetries = 3
'''
        symbols = extract_symbols(src)
        constants = [s for s in symbols if s.kind == "constant"]
        assert len(constants) == 1
        assert constants[0].name == "MaxRetries"

    def test_const_block(self) -> None:
        src = '''package main

const (
\tStatusOK     = 200
\tstatusError  = 500
)
'''
        symbols = extract_symbols(src)
        constants = [s for s in symbols if s.kind == "constant"]
        assert len(constants) == 2
        names = {c.name for c in constants}
        assert "StatusOK" in names
        assert "statusError" in names

    def test_var_block(self) -> None:
        src = '''package main

var (
\tErrTimeout = errors.New("timeout")
\tdefaultPort = 8080
)
'''
        symbols = extract_symbols(src)
        variables = [s for s in symbols if s.kind == "variable"]
        assert len(variables) == 2

    def test_multiple_symbol_kinds(self) -> None:
        src = '''package main

const Version = "1.0"

type Config struct {
\tPort int
}

func NewConfig() *Config {
\treturn &Config{Port: 8080}
}

var defaultConfig = NewConfig()
'''
        symbols = extract_symbols(src)
        kinds = {s.kind for s in symbols}
        assert "constant" in kinds
        assert "struct" in kinds
        assert "function" in kinds
        assert "variable" in kinds

    def test_init_function(self) -> None:
        src = '''package main

func init() {
\tlog.SetFlags(0)
}
'''
        symbols = extract_symbols(src)
        funcs = [s for s in symbols if s.kind == "function"]
        assert len(funcs) == 1
        assert funcs[0].name == "init"

    def test_main_function(self) -> None:
        src = '''package main

func main() {
\tfmt.Println("hello")
}
'''
        symbols = extract_symbols(src)
        funcs = [s for s in symbols if s.kind == "function"]
        assert len(funcs) == 1
        assert funcs[0].name == "main"

    def test_func_with_generic_type_params(self) -> None:
        src = '''package main

func Map[T any, U any](s []T, f func(T) U) []U {
}
'''
        symbols = extract_symbols(src)
        funcs = [s for s in symbols if s.kind == "function"]
        assert len(funcs) == 1
        assert funcs[0].name == "Map"

    def test_iota_const_block(self) -> None:
        src = '''package main

const (
\tRed = iota
\tGreen
\tBlue
)
'''
        symbols = extract_symbols(src)
        constants = [s for s in symbols if s.kind == "constant"]
        assert len(constants) == 3
        names = [c.name for c in constants]
        assert names == ["Red", "Green", "Blue"]

    def test_typed_const_block(self) -> None:
        src = '''package main

const (
\tA int = 1
\tB     = 2
)
'''
        symbols = extract_symbols(src)
        constants = [s for s in symbols if s.kind == "constant"]
        assert len(constants) == 2

    def test_typed_var_block(self) -> None:
        src = '''package main

var (
\tx int
\ty string
)
'''
        symbols = extract_symbols(src)
        variables = [s for s in symbols if s.kind == "variable"]
        assert len(variables) == 2


# ---------------------------------------------------------------------------
# Symbol references
# ---------------------------------------------------------------------------


class TestFindSymbolReferences:
    def test_function_call(self) -> None:
        src = '''package main

func main() {
\tresult := HandleRequest(ctx)
\tfmt.Println(result)
}
'''
        refs = find_symbol_references(src, "HandleRequest")
        assert len(refs) >= 1
        assert any(r.name == "HandleRequest" for r in refs)

    def test_type_reference(self) -> None:
        src = '''package main

func newServer() *Server {
\treturn &Server{}
}
'''
        refs = find_symbol_references(src, "Server")
        assert len(refs) >= 1

    def test_no_matches(self) -> None:
        src = '''package main

func main() {}
'''
        refs = find_symbol_references(src, "NonExistent")
        assert refs == []

    def test_does_not_match_substring(self) -> None:
        src = '''package main

func ServerHandler() {}
'''
        refs = find_symbol_references(src, "Server")
        # "Server" appears as part of "ServerHandler" — should NOT match as word boundary
        assert refs == []


# ---------------------------------------------------------------------------
# Import graph building
# ---------------------------------------------------------------------------


class TestBuildImportGraph:
    def test_simple_graph(self) -> None:
        files = {
            "cmd/main.go": '''package main

import (
\t"myapp/server"
\t"myapp/config"
)

func main() {}
''',
            "server/server.go": '''package server

import "myapp/config"

func Start() {}
''',
            "config/config.go": '''package config

func Load() {}
''',
        }
        graph = build_import_graph(files)
        assert "myapp/server" in graph["cmd/main.go"]
        assert "myapp/config" in graph["cmd/main.go"]
        assert "myapp/config" in graph["server/server.go"]
        assert graph["config/config.go"] == []

    def test_empty_files(self) -> None:
        graph = build_import_graph({})
        assert graph == {}


# ---------------------------------------------------------------------------
# Import chain verification
# ---------------------------------------------------------------------------


class TestVerifyImportChain:
    def test_direct_import(self) -> None:
        files = {
            "main.go": '''package main

import "myapp/server"

func main() {
\tserver.Start()
}
''',
            "server/server.go": '''package server

func Start() {}
''',
        }
        assert verify_import_chain(files, "main", "Start") is True

    def test_transitive_import(self) -> None:
        files = {
            "main.go": '''package main

import "myapp/server"

func main() {
\tserver.Run()
}
''',
            "server/server.go": '''package server

import "myapp/config"

func Run() {
\tconfig.Load()
}
''',
            "config/config.go": '''package config

func Load() {}
''',
        }
        assert verify_import_chain(files, "main", "Load") is True

    def test_no_chain(self) -> None:
        files = {
            "main.go": '''package main

func main() {}
''',
            "server/server.go": '''package server

func Start() {}
''',
        }
        assert verify_import_chain(files, "main", "Start") is False

    def test_circular_import_terminates(self) -> None:
        files = {
            "a.go": '''package a

import "myapp/b"

func DoA() {}
''',
            "b.go": '''package b

import "myapp/a"

func DoB() {}
''',
        }
        # Should terminate without infinite loop, returning False for a symbol
        # not defined in either
        assert verify_import_chain(files, "a", "NonExistent") is False


# ---------------------------------------------------------------------------
# GoParser class (wraps module functions, implements protocol)
# ---------------------------------------------------------------------------


class TestGoParserClass:
    def test_language(self, parser: GoParser) -> None:
        assert parser.language == "go"

    def test_extract_imports_delegation(self, parser: GoParser) -> None:
        src = 'package main\n\nimport "fmt"\n'
        imports = parser.extract_imports(src)
        assert len(imports) == 1
        assert imports[0].module == "fmt"

    def test_extract_symbols_delegation(self, parser: GoParser) -> None:
        src = "package main\n\nfunc Main() {}\n"
        symbols = parser.extract_symbols(src)
        assert len(symbols) >= 1

    def test_find_symbol_references_delegation(self, parser: GoParser) -> None:
        src = '''package main

func main() {
\tFoo()
}
'''
        refs = parser.find_symbol_references(src, "Foo")
        assert len(refs) >= 1
