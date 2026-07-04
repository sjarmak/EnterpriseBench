"""Tests for the Go edge extractor (scripts/mining/kg_graph_go.py).

Hermetic: runs against 3 mini Go repos under tests/fixtures/kg_miner_go/
(repo_goapp -> repo_golib -> repo_gobase via real Go import statements).
No network, no `go` toolchain — pure deterministic parsing.

The extractor must produce kg_graph.py's dataclasses (RepoGraph/ImportEdge/
Evidence/SymbolDef) so mine_cross_repo_paths and the task miner work unchanged.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "mining"))
sys.path.insert(0, str(REPO_ROOT / "lib"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "validation"))

import kg_graph  # noqa: E402
import kg_graph_go  # noqa: E402
import kg_task_miner  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "kg_miner_go"

FIXTURE_REPOS = {
    "repo_goapp": FIXTURES / "repo_goapp",
    "repo_golib": FIXTURES / "repo_golib",
    "repo_gobase": FIXTURES / "repo_gobase",
}

FIXTURE_REPO_META = {
    "repo_goapp": {"url": "https://github.com/example/repo_goapp", "rev": "deadbeef"},
    "repo_golib": {"url": "https://github.com/example/repo_golib", "rev": "deadbeef"},
    "repo_gobase": {"url": "https://github.com/example/repo_gobase", "rev": "deadbeef"},
}


@pytest.fixture(scope="module")
def graph() -> "kg_graph.RepoGraph":
    return kg_graph_go.build_graph_go(FIXTURE_REPOS)


def test_go_module_mapping_from_go_mod(graph):
    """Every go.mod module path maps to its repo, including the nested module
    (etcd-style multi-module repo: stats/go.mod inside repo_golib)."""
    assert graph.packages["example.com/goapp"] == "repo_goapp"
    assert graph.packages["example.com/golib"] == "repo_golib"
    assert graph.packages["example.com/golibstats"] == "repo_golib"
    assert graph.packages["example.com/gobase"] == "repo_gobase"


def test_import_block_parsing_with_evidence(graph):
    """The aliased import inside main.go's import block yields a module-import
    edge with exact file:line evidence and the verbatim import line."""
    edges = [
        e for e in graph.edges
        if e.edge_kind == "import"
        and e.evidence.file == "cmd/app/main.go"
        and e.dst_module == "example.com/golib/widget"
    ]
    assert len(edges) == 1, f"expected 1 widget import edge, got {edges}"
    edge = edges[0]
    assert edge.src_repo == "repo_goapp"
    assert edge.src_module == "example.com/goapp/cmd/app"
    assert edge.dst_repo == "repo_golib"
    assert edge.dst_symbol is None
    assert edge.crosses_repo
    assert edge.evidence.line == 7
    assert edge.evidence.statement == 'w "example.com/golib/widget"'

    # Stdlib import in the same block: kept as an external edge.
    fmt_edges = [
        e for e in graph.edges
        if e.evidence.file == "cmd/app/main.go" and e.dst_module == "fmt"
    ]
    assert len(fmt_edges) == 1
    assert fmt_edges[0].dst_repo is None
    assert not fmt_edges[0].crosses_repo


def test_single_form_import_with_alias(graph):
    """`import gw "example.com/golib/widget"` (single form) parses with the
    whole line as evidence, and the alias binds usage edges."""
    imp = [
        e for e in graph.edges
        if e.edge_kind == "import" and e.evidence.file == "pkg/report/report.go"
    ]
    assert len(imp) == 1
    assert imp[0].evidence.line == 3
    assert imp[0].evidence.statement == 'import gw "example.com/golib/widget"'

    usage = [
        e for e in graph.edges
        if e.edge_kind == "usage" and e.evidence.file == "pkg/report/report.go"
    ]
    assert len(usage) == 1
    assert usage[0].dst_symbol == "NewWidget"
    assert usage[0].dst_module == "example.com/golib/widget"
    assert usage[0].resolved is True


def test_usage_edges_respect_aliases(graph):
    """`w.NewWidget(...)` resolves through the alias to the defining package,
    with the first usage line as evidence; `w.Describe` resolves to widget's
    own Describe, not repo_gobase's same-named function."""
    new_widget = [
        e for e in graph.edges
        if e.edge_kind == "usage"
        and e.evidence.file == "cmd/app/main.go"
        and e.dst_symbol == "NewWidget"
    ]
    assert len(new_widget) == 1
    e = new_widget[0]
    assert e.dst_repo == "repo_golib"
    assert e.dst_module == "example.com/golib/widget"
    assert e.dst_kind == "function"
    assert e.resolved is True
    assert e.evidence.line == 14
    assert "w.NewWidget" in e.evidence.statement
    assert e.dst_node == "repo_golib:example.com/golib/widget.NewWidget"

    describe = [
        e for e in graph.edges
        if e.edge_kind == "usage"
        and e.evidence.file == "cmd/app/main.go"
        and e.dst_symbol == "Describe"
    ]
    assert len(describe) == 1
    assert describe[0].dst_module == "example.com/golib/widget"
    assert describe[0].dst_repo == "repo_golib"


def test_blank_and_dot_imports(graph):
    """Blank (`_`) imports produce a module-import edge but never a usage
    binding; dot (`.`) imports never produce usage edges either."""
    blank = [
        e for e in graph.edges
        if e.edge_kind == "import"
        and e.evidence.file == "widget/extra.go"
        and e.dst_module == "example.com/gobase/core"
    ]
    assert len(blank) == 1
    assert blank[0].dst_repo == "repo_gobase"

    # No usage edge sourced from extra.go: `ToUpper` (dot import) and the
    # blank-imported core package are both unbound.
    assert not [
        e for e in graph.edges
        if e.edge_kind == "usage" and e.evidence.file == "widget/extra.go"
    ]

    dot = [
        e for e in graph.edges
        if e.evidence.file == "widget/extra.go" and e.dst_module == "strings"
    ]
    assert len(dot) == 1
    assert dot[0].dst_repo is None


def test_test_files_and_skip_dirs_excluded(graph):
    """_test.go files never contribute nodes or edges."""
    assert not [e for e in graph.edges if e.evidence.file.endswith("_test.go")]


def test_intra_repo_nested_module_edge(graph):
    """widget -> example.com/golibstats crosses go.mod modules but stays in
    repo_golib: it must be an intra-repo edge (glue for path mining), never a
    cross-repo hop."""
    edges = [
        e for e in graph.edges
        if e.src_module == "example.com/golib/widget"
        and e.dst_module == "example.com/golibstats"
        and e.edge_kind == "import"
    ]
    assert len(edges) == 1
    assert edges[0].dst_repo == "repo_golib"
    assert not edges[0].crosses_repo

    count_usage = [
        e for e in graph.edges
        if e.edge_kind == "usage" and e.dst_symbol == "Count"
    ]
    assert len(count_usage) == 1
    assert count_usage[0].resolved is True


def test_binding_name_inference():
    """Unaliased import binding = last path segment, skipping a /vN major
    version suffix (Go module convention)."""
    assert kg_graph_go._binding_name("example.com/golib/widget") == "widget"
    assert kg_graph_go._binding_name("go.etcd.io/etcd/client/v3") == "client"
    assert kg_graph_go._binding_name("example.com/v2fake") == "v2fake"


def test_mine_cross_repo_paths_works_unchanged(graph):
    """kg_graph.mine_cross_repo_paths consumes the Go graph as-is and finds
    the goapp -> golib -> gobase 2-hop chain with per-hop evidence."""
    paths = kg_graph.mine_cross_repo_paths(graph, min_hops=2)
    assert paths, "expected at least one 2-hop cross-repo path"
    best = paths[0]
    assert best.repo_chain() == ("repo_goapp", "repo_golib", "repo_gobase")
    assert len(best.hops) == 2
    for hop in best.hops:
        assert hop.crosses_repo
        assert hop.evidence.file and hop.evidence.line >= 1
        assert hop.evidence.statement


def test_generate_task_from_go_path_passes_validation(graph):
    """The task miner emits a schema+semantic-valid, CRNT-passing task from a
    Go-mined path, with Go recorded as the language."""
    paths = kg_graph.mine_cross_repo_paths(graph, min_hops=2)
    task = kg_task_miner.generate_task(
        paths[0], FIXTURE_REPO_META, graph=graph, languages=["go"])
    assert task["metadata"]["languages"] == ["go"]
    errors = kg_task_miner.validate_task_dict(task)
    assert errors == [], f"validation errors: {errors}"
    crnt = kg_task_miner.run_crnt(task)
    assert crnt.passes_crnt, f"CRNT failed: {crnt}"
