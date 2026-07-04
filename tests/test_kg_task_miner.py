"""Tests for the KG-based task miner (scripts/mining/kg_graph.py + kg_task_miner.py).

Hermetic: runs against a tiny 3-repo fixture tree under tests/fixtures/kg_miner/
(repo_alpha -> repo_beta -> repo_gamma via real import statements). No network.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "mining"))
sys.path.insert(0, str(REPO_ROOT / "lib"))

import kg_graph  # noqa: E402
import kg_task_miner  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "kg_miner"

FIXTURE_REPOS = {
    "repo_alpha": FIXTURES / "repo_alpha",
    "repo_beta": FIXTURES / "repo_beta",
    "repo_gamma": FIXTURES / "repo_gamma",
}

FIXTURE_REPO_META = {
    "repo_alpha": {"url": "https://github.com/example/repo_alpha", "rev": "deadbeef"},
    "repo_beta": {"url": "https://github.com/example/repo_beta", "rev": "deadbeef"},
    "repo_gamma": {"url": "https://github.com/example/repo_gamma", "rev": "deadbeef"},
}


@pytest.fixture(scope="module")
def graph() -> "kg_graph.RepoGraph":
    return kg_graph.build_graph(FIXTURE_REPOS)


def test_import_edge_extraction_with_file_line_evidence(graph):
    """The `from beta import Widget` in alpha/client.py yields an edge with
    exact file:line evidence and the verbatim import statement."""
    edges = [
        e for e in graph.edges
        if e.src_repo == "repo_alpha"
        and e.evidence.file == "alpha/client.py"
        and e.dst_symbol == "Widget"
    ]
    assert len(edges) == 1, f"expected 1 Widget edge, got {edges}"
    edge = edges[0]
    assert edge.evidence.repo == "repo_alpha"
    assert edge.evidence.line == 2
    assert edge.evidence.statement == "from beta import Widget"


def test_cross_repo_edge_mapping_and_canonicalization(graph):
    """Top-level import names map to repos; `from beta import Widget` is
    canonicalized to the module that actually defines Widget (beta.core)."""
    cross = [e for e in graph.edges if e.crosses_repo]
    pairs = {(e.src_repo, e.dst_repo) for e in cross}
    assert ("repo_alpha", "repo_beta") in pairs
    assert ("repo_beta", "repo_gamma") in pairs

    widget_edge = next(
        e for e in cross
        if e.src_repo == "repo_alpha" and e.dst_symbol == "Widget"
    )
    # Canonicalization discipline: node id points at the DEFINING module,
    # not the package __init__ the symbol was imported through.
    assert widget_edge.dst_node == "repo_beta:beta.core.Widget"
    assert widget_edge.resolved is True

    helper_edge = next(
        e for e in cross
        if e.src_repo == "repo_beta" and e.dst_symbol == "helper"
    )
    assert helper_edge.dst_node == "repo_gamma:gamma.util.helper"

    # Intra-repo relative import is captured but NOT a cross-repo edge.
    intra = [
        e for e in graph.edges
        if e.src_repo == "repo_alpha" and e.dst_symbol == "Settings"
    ]
    assert intra and not intra[0].crosses_repo


def test_path_mining_rejects_intra_repo_only_paths(graph):
    """Every hop of every mined path must cross a repo boundary; the
    alpha->alpha.config edge never appears in a mined path."""
    paths = kg_graph.mine_cross_repo_paths(graph, min_hops=2)
    assert paths, "expected at least one 2-hop cross-repo path"
    for path in paths:
        for hop in path.hops:
            assert hop.crosses_repo, f"intra-repo hop leaked into path: {hop}"
            assert hop.evidence.file and hop.evidence.line >= 1
        assert "repo_alpha:alpha.config.Settings" not in [
            h.dst_node for h in path.hops
        ]

    best = paths[0]
    assert best.repo_chain() == ("repo_alpha", "repo_beta", "repo_gamma")
    assert len(best.hops) == 2


def test_emitted_task_json_passes_schema_and_semantics(graph, tmp_path):
    """The generated task dict validates against schemas/task.schema.json and
    the eb_verify semantic layer, and passes structural CRNT."""
    paths = kg_graph.mine_cross_repo_paths(graph, min_hops=2)
    task = kg_task_miner.generate_task(paths[0], FIXTURE_REPO_META, task_number=1)

    # Round-trip through JSON to prove serializability.
    task = json.loads(json.dumps(task))

    errors = kg_task_miner.validate_task_dict(task)
    assert errors == [], f"validation errors: {errors}"

    # Structural CRNT: every repo on the path has a required_file.
    crnt = kg_task_miner.run_crnt(task)
    assert crnt.passes_crnt, f"CRNT failed: {crnt}"

    # One checkpoint per hop, each carrying the evidence tuple.
    assert len(task["checkpoints"]) == len(paths[0].hops)
    for cp, hop in zip(task["checkpoints"], paths[0].hops):
        assert hop.evidence.file in cp["description"]
        assert f"line {hop.evidence.line}" in cp["description"]
        assert hop.evidence.statement in cp["description"]
    assert abs(sum(cp["weight"] for cp in task["checkpoints"]) - 1.0) < 0.01

    # Difficulty stratum derives from repo count on the path (3 -> tri_repo).
    assert task["difficulty_stratum"] == "tri_repo"


# -----------------------------------------------------------------------------
# Structural-diversity grouping (improvement a)
# -----------------------------------------------------------------------------

def test_structural_signature_groups_by_module_chain(graph):
    """Paths that differ only in the terminal symbol share one structural
    signature; a path through different modules gets a different one."""
    paths = kg_graph.mine_cross_repo_paths(graph, min_hops=2)
    helper_paths = [
        p for p in paths if p.hops[-1].dst_symbol in ("helper", "helper2")
    ]
    assert len(helper_paths) == 2
    sig_a, sig_b = (kg_graph.structural_signature(p) for p in helper_paths)
    assert sig_a == sig_b

    fmt_path = next(p for p in paths if p.hops[-1].dst_symbol == "fmt")
    assert kg_graph.structural_signature(fmt_path) != sig_a

    # The terminal MODULE is excluded too, not just the terminal symbol: the
    # group is defined by (start module, hop-1 target, hop-2 source, ...) —
    # two paths landing in different terminal modules of the same repo via
    # the same structure collapse into one group.
    e1 = _edge("import", "A")
    e2a = _edge("usage", "P", src_repo="repo_y", src_module="y.core",
                dst_repo="repo_z", dst_module="z.one", statement="z.P")
    e2b = _edge("usage", "Q", src_repo="repo_y", src_module="y.core",
                dst_repo="repo_z", dst_module="z.two", statement="z.Q")
    p1 = kg_graph.MinedPath(hops=(e1, e2a), glue_chains=((),))
    p2 = kg_graph.MinedPath(hops=(e1, e2b), glue_chains=((),))
    assert kg_graph.structural_signature(p1) == kg_graph.structural_signature(p2)


def test_structural_grouping_is_deterministic(graph):
    """Rebuilding the graph and re-mining yields identical path order and
    identical signatures."""
    paths = kg_graph.mine_cross_repo_paths(graph, min_hops=2)
    graph2 = kg_graph.build_graph(FIXTURE_REPOS)
    paths2 = kg_graph.mine_cross_repo_paths(graph2, min_hops=2)
    assert [p.node_chain() for p in paths2] == [p.node_chain() for p in paths]
    assert [kg_graph.structural_signature(p) for p in paths2] == [
        kg_graph.structural_signature(p) for p in paths
    ]


def test_select_diverse_one_representative_per_group(graph):
    """--top selection returns one representative per structural group (the
    group's highest-ranked path), overflowing into second representatives
    only after every group is represented."""
    paths = kg_graph.mine_cross_repo_paths(graph, min_hops=2)
    sigs = [kg_graph.structural_signature(p) for p in paths]
    n_groups = len(set(sigs))
    assert n_groups == 2  # fixture: {client->core->util}, {pipeline->extras->textutil}

    top2 = kg_graph.select_diverse(paths, 2)
    assert len(top2) == 2
    assert top2[0] is paths[0]  # best group's representative is the global best
    assert (
        kg_graph.structural_signature(top2[0])
        != kg_graph.structural_signature(top2[1])
    )

    # Overflow: 3 requested, only 2 groups -> second representative of the
    # first group (next-ranked member) fills the last slot.
    top3 = kg_graph.select_diverse(paths, 3)
    assert len(top3) == 3
    assert kg_graph.structural_signature(top3[2]) == kg_graph.structural_signature(top3[0])
    assert top3[2] is not top3[0]

    # Requesting more than exists returns everything, no duplicates.
    everything = kg_graph.select_diverse(paths, 100)
    assert len(everything) == len(paths)
    assert len({id(p) for p in everything}) == len(paths)


# -----------------------------------------------------------------------------
# Emitted checkpoint verifier scripts (improvement b)
# -----------------------------------------------------------------------------

def _run_check(script: Path, workspace: Path) -> tuple[int, dict]:
    import os
    import subprocess

    result = subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        env={**os.environ, "WORKSPACE": str(workspace)},
    )
    return result.returncode, json.loads(result.stdout.strip())


def test_emitted_check_scripts_verify_hop_evidence(graph, tmp_path):
    import os
    import shutil

    paths = kg_graph.mine_cross_repo_paths(graph, min_hops=2)
    path = paths[0]
    task = kg_task_miner.generate_task(path, FIXTURE_REPO_META, graph=graph)
    checks_dir = tmp_path / "task" / "checks"
    scripts = kg_task_miner.emit_check_scripts(path, checks_dir)

    # One executable script per hop, named as the checkpoints reference them.
    assert [s.name for s in scripts] == [
        f"check_hop_{i + 1}.sh" for i in range(len(path.hops))
    ]
    for script in scripts:
        assert script.is_file()
        assert os.access(script, os.X_OK), f"not executable: {script}"
    assert [cp["verifier"] for cp in task["checkpoints"]] == [
        f"checks/{s.name}" for s in scripts
    ]

    # PASS: fixture tree is the workspace (workspace/{repo}/{file} layout).
    for script in scripts:
        code, data = _run_check(script, FIXTURES)
        assert code == 0, f"{script.name} failed: {data}"
        assert data["score"] == 1.0
        assert data["passed"] is True

    # FAIL: evidence file exists but the verbatim statement was removed.
    tampered = tmp_path / "ws_tampered"
    shutil.copytree(FIXTURES, tampered)
    ev = path.hops[0].evidence
    target = tampered / ev.repo / ev.file
    target.write_text(
        target.read_text().replace(ev.statement, "# statement removed"))
    code, data = _run_check(scripts[0], tampered)
    assert code != 0
    assert data["score"] == 0.0
    assert data["passed"] is False

    # FAIL: evidence file missing entirely.
    empty_ws = tmp_path / "ws_empty"
    empty_ws.mkdir()
    code, data = _run_check(scripts[0], empty_ws)
    assert code != 0
    assert data["score"] == 0.0
    assert "missing" in data["detail"].lower()


def test_check_scripts_resist_shell_metacharacter_injection(tmp_path):
    """Adversarial regression: a mined evidence statement carrying shell
    metacharacters (quote-break, `...`, $(...), $$) must never execute as
    code when the emitted check script runs — shlex.quote + env-var passing
    must keep it inert while the JSON verdict stays correct."""
    import glob

    marker = tmp_path / "kg_pwned_marker"
    inj = (
        f"'; touch {marker} /tmp/kg_pwned_$$; # "
        f"`touch {marker}` $(touch {marker})"
    )
    tmp_pwned_before = set(glob.glob("/tmp/kg_pwned_*"))

    hops = (
        _edge("import", "Thing", statement=inj),
        _edge("import", "leaf", src_repo="repo_y", src_module="y.core",
              dst_repo="repo_z", dst_module="z.util",
              statement="from z.util import leaf"),
    )
    path = kg_graph.MinedPath(hops=hops, glue_chains=((),))
    scripts = kg_task_miner.emit_check_scripts(path, tmp_path / "checks")

    # Evidence PRESENT: file contains the adversarial statement verbatim.
    ws = tmp_path / "ws_present"
    (ws / "repo_x" / "x").mkdir(parents=True)
    (ws / "repo_x" / "x" / "entry.py").write_text(inj + "\n")
    code, data = _run_check(scripts[0], ws)
    assert code == 0
    assert data["passed"] is True
    assert data["score"] == 1.0

    # Evidence ABSENT: file exists without the statement — clean JSON fail.
    ws2 = tmp_path / "ws_absent"
    (ws2 / "repo_x" / "x").mkdir(parents=True)
    (ws2 / "repo_x" / "x" / "entry.py").write_text("benign content only\n")
    code, data = _run_check(scripts[0], ws2)
    assert code != 0
    assert data["passed"] is False
    assert data["score"] == 0.0

    # No injected command ever executed.
    assert not marker.exists(), "shell injection executed via evidence statement"
    assert set(glob.glob("/tmp/kg_pwned_*")) == tmp_pwned_before


# -----------------------------------------------------------------------------
# Prompt wording per edge kind (improvement c)
# -----------------------------------------------------------------------------

def _edge(edge_kind: str, symbol: str | None, *, src_repo="repo_x",
          src_module="x.entry", dst_repo="repo_y", dst_module="y.core",
          statement="from y import Thing", line=1) -> "kg_graph.ImportEdge":
    return kg_graph.ImportEdge(
        src_repo=src_repo, src_module=src_module, dst_repo=dst_repo,
        dst_module=dst_module, dst_symbol=symbol, dst_kind="class",
        resolved=True,
        evidence=kg_graph.Evidence(src_repo, "x/entry.py", line, statement),
        edge_kind=edge_kind,
    )


_XYZ_META = {
    "repo_x": {"url": "https://github.com/example/repo_x", "rev": "deadbeef"},
    "repo_y": {"url": "https://github.com/example/repo_y", "rev": "deadbeef"},
    "repo_z": {"url": "https://github.com/example/repo_z", "rev": "deadbeef"},
}


def test_prompt_wording_for_import_kind_edge(graph):
    """A symbol-import first hop keeps the 'imports X from Y' wording."""
    paths = kg_graph.mine_cross_repo_paths(graph, min_hops=2)
    task = kg_task_miner.generate_task(paths[0], FIXTURE_REPO_META, graph=graph)
    prompt = task["task"]["prompt"]
    assert "imports `Widget` from repo_beta" in prompt


def test_prompt_wording_for_usage_kind_edge():
    """A usage-kind first hop (bare `import pkg` + attribute access) must NOT
    claim a from-import; it names the module import and the attribute use."""
    hops = (
        _edge("usage", "Thing",
              statement="y.Thing()"),
        _edge("import", "leaf", src_repo="repo_y", src_module="y.core",
              dst_repo="repo_z", dst_module="z.util",
              statement="from z.util import leaf"),
    )
    path = kg_graph.MinedPath(hops=hops, glue_chains=((),))
    task = kg_task_miner.generate_task(path, _XYZ_META)
    prompt = task["task"]["prompt"]
    assert "imports `Thing` from repo_y" not in prompt
    assert "imports the `y` module from repo_y" in prompt
    assert "accesses `Thing` on it" in prompt


def test_prompt_wording_for_bare_module_import_edge():
    """A bare module-import first hop (no symbol) names the module, not a
    nonexistent symbol."""
    hops = (
        _edge("import", None, statement="import y.core"),
        _edge("import", "leaf", src_repo="repo_y", src_module="y.core",
              dst_repo="repo_z", dst_module="z.util",
              statement="from z.util import leaf"),
    )
    path = kg_graph.MinedPath(hops=hops, glue_chains=((),))
    task = kg_task_miner.generate_task(path, _XYZ_META)
    prompt = task["task"]["prompt"]
    assert "imports the `y.core` module from repo_y" in prompt


# -----------------------------------------------------------------------------
# Difficulty calibration (improvement d)
# -----------------------------------------------------------------------------

def test_difficulty_calibration_by_hop_count(graph):
    """2-hop -> medium/30min; >=3-hop -> hard; stratum still tracks repo count."""
    paths = kg_graph.mine_cross_repo_paths(graph, min_hops=2)
    task2 = kg_task_miner.generate_task(paths[0], FIXTURE_REPO_META, graph=graph)
    assert task2["task"]["difficulty"] == "medium"
    assert task2["task"]["estimated_duration_minutes"] == 30
    assert task2["difficulty_stratum"] == "tri_repo"

    meta4 = dict(_XYZ_META)
    meta4["repo_w"] = {"url": "https://github.com/example/repo_w", "rev": "deadbeef"}
    hops = (
        _edge("import", "Thing"),
        _edge("import", "leaf", src_repo="repo_y", src_module="y.core",
              dst_repo="repo_z", dst_module="z.util",
              statement="from z.util import leaf"),
        _edge("import", "deep", src_repo="repo_z", src_module="z.util",
              dst_repo="repo_w", dst_module="w.base",
              statement="from w.base import deep"),
    )
    path3 = kg_graph.MinedPath(hops=hops, glue_chains=((), ()))
    task3 = kg_task_miner.generate_task(path3, meta4)
    assert task3["task"]["difficulty"] == "hard"
    assert task3["task"]["estimated_duration_minutes"] == 45
    assert task3["difficulty_stratum"] == "multi_repo"
