"""
Tests for manifest parsers -- npm, Go, Python.

TDD: tests written first, then implementation.
"""

from __future__ import annotations

import json
import textwrap

import pytest

from eb_verify.parsers.manifests import (
    Dependency,
    DependencyGraph,
    ManifestInfo,
    build_go_dep_graph,
    build_npm_dep_graph,
    build_python_dep_graph,
    find_dep_path,
    is_transitive_dep,
    parse_go_mod,
    parse_go_sum,
    parse_package_json,
    parse_package_lock,
    parse_pyproject_toml,
    parse_requirements_txt,
    parse_setup_cfg,
)

# ---------------------------------------------------------------------------
# Common types
# ---------------------------------------------------------------------------


class TestDependencyGraph:
    def test_empty_graph(self) -> None:
        g = DependencyGraph()
        assert g.nodes() == set()
        assert g.edges_from("anything") == []

    def test_add_edge(self) -> None:
        g = DependencyGraph()
        g.add_edge("A", "B", "^1.0")
        assert "A" in g.nodes()
        assert "B" in g.nodes()
        edges = g.edges_from("A")
        assert len(edges) == 1
        assert edges[0] == ("B", "^1.0")

    def test_transitive_reachability(self) -> None:
        g = DependencyGraph()
        g.add_edge("A", "B", "^1.0")
        g.add_edge("B", "C", "^2.0")
        g.add_edge("C", "D", "^3.0")
        assert is_transitive_dep(g, "A", "D") is True
        assert is_transitive_dep(g, "A", "B") is True
        assert is_transitive_dep(g, "D", "A") is False

    def test_find_dep_path(self) -> None:
        g = DependencyGraph()
        g.add_edge("A", "B", "^1.0")
        g.add_edge("B", "C", "^2.0")
        path = find_dep_path(g, "A", "C")
        assert path == ["A", "B", "C"]

    def test_find_dep_path_no_path(self) -> None:
        g = DependencyGraph()
        g.add_edge("A", "B", "^1.0")
        path = find_dep_path(g, "A", "Z")
        assert path == []

    def test_find_dep_path_direct(self) -> None:
        g = DependencyGraph()
        g.add_edge("A", "B", "^1.0")
        path = find_dep_path(g, "A", "B")
        assert path == ["A", "B"]

    def test_cycle_detection(self) -> None:
        g = DependencyGraph()
        g.add_edge("A", "B", "")
        g.add_edge("B", "C", "")
        g.add_edge("C", "A", "")
        assert is_transitive_dep(g, "A", "C") is True
        path = find_dep_path(g, "A", "C")
        assert path == ["A", "B", "C"]


# ---------------------------------------------------------------------------
# npm parsers
# ---------------------------------------------------------------------------


class TestNpmParser:
    SIMPLE_PKG = json.dumps(
        {
            "name": "my-app",
            "version": "1.0.0",
            "dependencies": {
                "lodash": "^4.17.20",
                "express": "~4.18.0",
            },
            "devDependencies": {
                "jest": "^29.0.0",
            },
            "peerDependencies": {
                "react": ">=16.8.0",
            },
        }
    )

    def test_parse_name_version(self) -> None:
        info = parse_package_json(self.SIMPLE_PKG)
        assert info.name == "my-app"
        assert info.version == "1.0.0"

    def test_parse_dependencies(self) -> None:
        info = parse_package_json(self.SIMPLE_PKG)
        dep_names = {d.name for d in info.dependencies}
        assert "lodash" in dep_names
        assert "express" in dep_names

    def test_parse_dev_dependencies(self) -> None:
        info = parse_package_json(self.SIMPLE_PKG)
        dev_names = {d.name for d in info.dev_dependencies}
        assert "jest" in dev_names

    def test_parse_peer_dependencies(self) -> None:
        info = parse_package_json(self.SIMPLE_PKG)
        peer_names = {d.name for d in info.peer_dependencies}
        assert "react" in peer_names

    def test_version_constraint_preserved(self) -> None:
        info = parse_package_json(self.SIMPLE_PKG)
        lodash = next(d for d in info.dependencies if d.name == "lodash")
        assert lodash.version_constraint == "^4.17.20"

    def test_empty_package_json(self) -> None:
        info = parse_package_json("{}")
        assert info.name == ""
        assert info.version == ""
        assert info.dependencies == []

    def test_no_version_field(self) -> None:
        info = parse_package_json(json.dumps({"name": "x"}))
        assert info.name == "x"
        assert info.version == ""

    def test_workspace_package_refs(self) -> None:
        pkg = json.dumps(
            {
                "name": "monorepo-root",
                "version": "1.0.0",
                "dependencies": {
                    "@scope/pkg-a": "workspace:*",
                    "lodash": "^4.17.21",
                },
            }
        )
        info = parse_package_json(pkg)
        ws_dep = next(d for d in info.dependencies if d.name == "@scope/pkg-a")
        assert ws_dep.version_constraint == "workspace:*"

    def test_build_npm_dep_graph(self) -> None:
        pkgs = {
            "app": json.dumps(
                {
                    "name": "app",
                    "version": "1.0.0",
                    "dependencies": {"lib-a": "^1.0.0"},
                }
            ),
            "lib-a": json.dumps(
                {
                    "name": "lib-a",
                    "version": "1.0.0",
                    "dependencies": {"lodash": "^4.17.20"},
                }
            ),
        }
        graph = build_npm_dep_graph(pkgs)
        assert is_transitive_dep(graph, "app", "lodash")
        path = find_dep_path(graph, "app", "lodash")
        assert path == ["app", "lib-a", "lodash"]


class TestNpmLockParser:
    LOCK_V3 = json.dumps(
        {
            "name": "my-app",
            "lockfileVersion": 3,
            "packages": {
                "": {"name": "my-app", "version": "1.0.0"},
                "node_modules/lodash": {
                    "version": "4.17.21",
                    "resolved": "https://registry.npmjs.org/lodash/-/lodash-4.17.21.tgz",
                },
                "node_modules/express": {
                    "version": "4.18.2",
                    "dependencies": {
                        "body-parser": "1.20.1",
                    },
                },
            },
        }
    )

    def test_parse_lock_extracts_versions(self) -> None:
        result = parse_package_lock(self.LOCK_V3)
        assert result["lodash"] == "4.17.21"
        assert result["express"] == "4.18.2"

    def test_parse_lock_empty(self) -> None:
        result = parse_package_lock("{}")
        assert result == {}


# ---------------------------------------------------------------------------
# Go module parsers
# ---------------------------------------------------------------------------


class TestGoModParser:
    GO_MOD = textwrap.dedent("""\
        module github.com/example/myproject

        go 1.21

        require (
        \tgolang.org/x/net v0.6.0
        \tgoogle.golang.org/grpc v1.53.0
        )

        require (
        \tgolang.org/x/text v0.7.0 // indirect
        )

        replace golang.org/x/net => golang.org/x/net v0.8.0

        exclude golang.org/x/crypto v0.1.0
    """)

    def test_parse_module_path(self) -> None:
        info = parse_go_mod(self.GO_MOD)
        assert info.name == "github.com/example/myproject"

    def test_parse_go_version(self) -> None:
        info = parse_go_mod(self.GO_MOD)
        assert info.version == "1.21"

    def test_parse_require_direct(self) -> None:
        info = parse_go_mod(self.GO_MOD)
        dep_names = {d.name for d in info.dependencies if not d.optional}
        assert "golang.org/x/net" in dep_names
        assert "google.golang.org/grpc" in dep_names

    def test_parse_require_indirect(self) -> None:
        info = parse_go_mod(self.GO_MOD)
        indirect = [d for d in info.dependencies if d.optional]
        assert any(d.name == "golang.org/x/text" for d in indirect)

    def test_parse_version_constraint(self) -> None:
        info = parse_go_mod(self.GO_MOD)
        xnet = next(d for d in info.dependencies if d.name == "golang.org/x/net")
        assert xnet.version_constraint == "v0.6.0"

    def test_parse_replace(self) -> None:
        info = parse_go_mod(self.GO_MOD)
        assert "golang.org/x/net" in info.extra.get("replace", {})
        assert info.extra["replace"]["golang.org/x/net"] == "golang.org/x/net v0.8.0"

    def test_parse_exclude(self) -> None:
        info = parse_go_mod(self.GO_MOD)
        assert "golang.org/x/crypto v0.1.0" in info.extra.get("exclude", [])

    def test_empty_go_mod(self) -> None:
        info = parse_go_mod("module example.com/empty\n\ngo 1.20\n")
        assert info.name == "example.com/empty"
        assert info.dependencies == []

    def test_single_require(self) -> None:
        mod = "module m\n\ngo 1.20\n\nrequire golang.org/x/net v0.5.0\n"
        info = parse_go_mod(mod)
        assert len(info.dependencies) == 1
        assert info.dependencies[0].name == "golang.org/x/net"

    def test_build_go_dep_graph(self) -> None:
        mods = {
            "prometheus": textwrap.dedent("""\
                module github.com/prometheus/prometheus

                go 1.20

                require (
                \tgolang.org/x/net v0.5.0
                \tgoogle.golang.org/grpc v1.50.0
                )
            """),
            "grpc-go": textwrap.dedent("""\
                module google.golang.org/grpc

                go 1.19

                require (
                \tgolang.org/x/net v0.4.0
                )
            """),
        }
        graph = build_go_dep_graph(mods)
        assert is_transitive_dep(
            graph, "github.com/prometheus/prometheus", "golang.org/x/net"
        )
        path = find_dep_path(
            graph,
            "github.com/prometheus/prometheus",
            "golang.org/x/net",
        )
        assert path == [
            "github.com/prometheus/prometheus",
            "golang.org/x/net",
        ]


class TestGoSumParser:
    GO_SUM = textwrap.dedent("""\
        golang.org/x/net v0.6.0 h1:abc123=
        golang.org/x/net v0.6.0/go.mod h1:def456=
        google.golang.org/grpc v1.53.0 h1:ghi789=
        google.golang.org/grpc v1.53.0/go.mod h1:jkl012=
    """)

    def test_parse_go_sum(self) -> None:
        result = parse_go_sum(self.GO_SUM)
        assert "golang.org/x/net" in result
        assert result["golang.org/x/net"]["version"] == "v0.6.0"

    def test_parse_go_sum_empty(self) -> None:
        result = parse_go_sum("")
        assert result == {}


# ---------------------------------------------------------------------------
# Python parsers
# ---------------------------------------------------------------------------


class TestRequirementsTxtParser:
    REQS = textwrap.dedent("""\
        # Core dependencies
        flask>=2.0,<3.0
        requests==2.28.1
        sqlalchemy~=2.0

        # Optional
        redis>=4.0  # cache backend

        -r base.txt
        --find-links https://example.com/wheels
    """)

    def test_parse_packages(self) -> None:
        deps = parse_requirements_txt(self.REQS)
        names = {d.name for d in deps}
        assert "flask" in names
        assert "requests" in names
        assert "sqlalchemy" in names
        assert "redis" in names

    def test_parse_version_constraints(self) -> None:
        deps = parse_requirements_txt(self.REQS)
        flask = next(d for d in deps if d.name == "flask")
        assert flask.version_constraint == ">=2.0,<3.0"
        requests_dep = next(d for d in deps if d.name == "requests")
        assert requests_dep.version_constraint == "==2.28.1"

    def test_ignores_comments(self) -> None:
        deps = parse_requirements_txt(self.REQS)
        names = {d.name for d in deps}
        assert "cache" not in names

    def test_ignores_flags(self) -> None:
        deps = parse_requirements_txt(self.REQS)
        names = {d.name for d in deps}
        assert "-r" not in names
        assert "--find-links" not in names

    def test_empty_requirements(self) -> None:
        deps = parse_requirements_txt("")
        assert deps == []

    def test_pinned_only(self) -> None:
        deps = parse_requirements_txt("numpy==1.24.0\npandas==1.5.3\n")
        assert len(deps) == 2
        assert deps[0].version_constraint == "==1.24.0"

    def test_extras(self) -> None:
        deps = parse_requirements_txt("sqlalchemy[asyncio]>=2.0\n")
        assert deps[0].name == "sqlalchemy[asyncio]"
        assert deps[0].version_constraint == ">=2.0"

    def test_includes_tracked(self) -> None:
        """The -r lines are tracked as includes, not as deps."""
        deps = parse_requirements_txt(self.REQS)
        names = {d.name for d in deps}
        assert "base.txt" not in names


class TestSetupCfgParser:
    SETUP_CFG = textwrap.dedent("""\
        [metadata]
        name = my-package
        version = 1.2.3

        [options]
        install_requires =
            flask>=2.0
            requests==2.28.1
            sqlalchemy~=2.0

        [options.extras_require]
        dev =
            pytest>=7.0
            black
        redis =
            redis>=4.0
    """)

    def test_parse_name_version(self) -> None:
        info = parse_setup_cfg(self.SETUP_CFG)
        assert info.name == "my-package"
        assert info.version == "1.2.3"

    def test_parse_install_requires(self) -> None:
        info = parse_setup_cfg(self.SETUP_CFG)
        names = {d.name for d in info.dependencies}
        assert "flask" in names
        assert "requests" in names
        assert "sqlalchemy" in names

    def test_parse_extras_require(self) -> None:
        info = parse_setup_cfg(self.SETUP_CFG)
        extras = info.extra.get("extras_require", {})
        assert "dev" in extras
        assert "redis" in extras

    def test_empty_setup_cfg(self) -> None:
        info = parse_setup_cfg("[metadata]\nname = empty\n")
        assert info.name == "empty"
        assert info.dependencies == []


class TestPyprojectTomlParser:
    PYPROJECT = textwrap.dedent("""\
        [project]
        name = "my-package"
        version = "2.0.0"
        dependencies = [
            "flask>=2.0",
            "requests==2.28.1",
            "sqlalchemy~=2.0",
        ]

        [project.optional-dependencies]
        dev = [
            "pytest>=7.0",
            "black",
        ]
    """)

    def test_parse_name_version(self) -> None:
        info = parse_pyproject_toml(self.PYPROJECT)
        assert info.name == "my-package"
        assert info.version == "2.0.0"

    def test_parse_dependencies(self) -> None:
        info = parse_pyproject_toml(self.PYPROJECT)
        names = {d.name for d in info.dependencies}
        assert "flask" in names
        assert "requests" in names

    def test_parse_optional_dependencies(self) -> None:
        info = parse_pyproject_toml(self.PYPROJECT)
        extras = info.extra.get("optional_dependencies", {})
        assert "dev" in extras

    def test_empty_pyproject(self) -> None:
        info = parse_pyproject_toml("[project]\nname = 'empty'\n")
        assert info.name == "empty"
        assert info.dependencies == []

    def test_no_project_section(self) -> None:
        info = parse_pyproject_toml("[tool.black]\nline-length = 88\n")
        assert info.name == ""
        assert info.dependencies == []


class TestBuildPythonDepGraph:
    def test_simple_graph(self) -> None:
        manifests = {
            "app": textwrap.dedent("""\
                [project]
                name = "app"
                version = "1.0.0"
                dependencies = [
                    "lib-a>=1.0",
                ]
            """),
            "lib-a": textwrap.dedent("""\
                [project]
                name = "lib-a"
                version = "1.0.0"
                dependencies = [
                    "requests>=2.28",
                ]
            """),
        }
        graph = build_python_dep_graph(manifests)
        assert is_transitive_dep(graph, "app", "requests")
        path = find_dep_path(graph, "app", "requests")
        assert path == ["app", "lib-a", "requests"]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_malformed_package_json(self) -> None:
        """Malformed JSON should raise ValueError."""
        with pytest.raises(ValueError):
            parse_package_json("not json {{{")

    def test_malformed_go_mod_no_module(self) -> None:
        """go.mod without module line should still parse (empty name)."""
        info = parse_go_mod("go 1.20\n")
        assert info.name == ""

    def test_requirements_with_hashes(self) -> None:
        reqs = textwrap.dedent("""\
            requests==2.28.1 \\
                --hash=sha256:abc123
            flask>=2.0
        """)
        deps = parse_requirements_txt(reqs)
        names = {d.name for d in deps}
        assert "requests" in names
        assert "flask" in names

    def test_go_mod_retract(self) -> None:
        """retract directives should be ignored gracefully."""
        mod = textwrap.dedent("""\
            module example.com/m

            go 1.21

            retract v1.0.0

            require golang.org/x/net v0.5.0
        """)
        info = parse_go_mod(mod)
        assert len(info.dependencies) == 1
