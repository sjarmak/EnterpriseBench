"""Tests for REFACTOR_PLAN.md ordering extraction (EnterpriseBench-e1eq).

check_topo_order.sh's original extraction regex assumed the agent's proposed
ordering is always a flat "1. reponame" markdown list. Real completed runs
instead use "### Step N — <description>" headings (with the actual repo
named on a separate "**Repo:** `<repo>`" line) or plain "Step N — <repo>"
lines, and reference repos by narrative module path ("go.etcd.io/etcd")
rather than the literal "org/repo" dependency-graph key ("etcd-io/etcd").

These tests use 3 real completed baseline runs
(results/rerun_pt0n/refactor-orch-{001,004,007}/baseline/REFACTOR_PLAN.md,
copied into tests/fixtures/) as fixtures, verified independently correct
against ground truth, that previously scored 0.0 due to this mismatch.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from eb_verify.plugins.topological_order import (
    extract_proposed_order,
    resolve_tokens_to_graph,
    validate_refactor_plan_markdown,
    validate_topological_order,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "refactor_orchestration"


def _load(task_num: str) -> str:
    path = FIXTURES_DIR / f"refactor-orch-{task_num}-baseline-REFACTOR_PLAN.md"
    return path.read_text()


# Real ground_truth.json dependency graphs for the 3 fixture tasks.
GRAPH_001 = {
    "etcd-io/etcd": [],
    "kubernetes/kubernetes": ["etcd-io/etcd"],
}
GRAPH_004 = {
    "protocolbuffers/protobuf-go": [],
    "grpc/grpc-go": ["protocolbuffers/protobuf-go"],
    "etcd-io/etcd": ["grpc/grpc-go", "protocolbuffers/protobuf-go"],
}
GRAPH_007 = {
    "grpc/grpc-go": [],
    "etcd-io/etcd": ["grpc/grpc-go"],
    "kubernetes/kubernetes": ["grpc/grpc-go", "etcd-io/etcd"],
}


class TestExtractProposedOrderRealFixtures:
    """extract_proposed_order must pull step tokens out of each real markdown shape."""

    def test_001_step_headings_with_repo_field(self) -> None:
        # "### Step N — <narrative description>" headings; actual repo lives
        # on a separate "**Repo:** `<repo>`" line inside each step's block.
        tokens = extract_proposed_order(_load("001"))
        assert tokens == [
            "go.etcd.io/etcd",
            "kubernetes/kubernetes",
            "kubernetes/kubernetes",
            "kubernetes/kubernetes",
            "kubernetes/kubernetes",
            "kubernetes/kubernetes",
        ]

    def test_004_plain_step_lines_in_code_fence(self) -> None:
        # "Step N — <repo> (...)" plain lines inside a fenced code block, no
        # separate Repo: field — the repo token is right after the dash.
        tokens = extract_proposed_order(_load("004"))
        assert tokens == ["protobuf-go", "grpc-go", "etcd"]

    def test_007_flat_bolded_numbered_list(self) -> None:
        # "N. **repo** (...) — description" flat markdown numbered list.
        tokens = extract_proposed_order(_load("007"))
        assert tokens == ["grpc-go", "etcd", "kubernetes"]


class TestResolveTokensToGraph:
    """Narrative tokens must resolve to the literal org/repo graph keys."""

    def test_001_resolves_to_two_graph_keys_in_order(self) -> None:
        tokens = extract_proposed_order(_load("001"))
        resolved = resolve_tokens_to_graph(tokens, GRAPH_001.keys())
        assert resolved == ["etcd-io/etcd", "kubernetes/kubernetes"]

    def test_004_resolves_to_three_graph_keys_in_order(self) -> None:
        tokens = extract_proposed_order(_load("004"))
        resolved = resolve_tokens_to_graph(tokens, GRAPH_004.keys())
        assert resolved == [
            "protocolbuffers/protobuf-go",
            "grpc/grpc-go",
            "etcd-io/etcd",
        ]

    def test_007_resolves_to_three_graph_keys_in_order(self) -> None:
        tokens = extract_proposed_order(_load("007"))
        resolved = resolve_tokens_to_graph(tokens, GRAPH_007.keys())
        assert resolved == [
            "grpc/grpc-go",
            "etcd-io/etcd",
            "kubernetes/kubernetes",
        ]


class TestRealBaselinesScoreCorrectly:
    """The 3 known-good baselines must score as valid orderings, not 0.0."""

    @pytest.mark.parametrize(
        "task_num,graph",
        [("001", GRAPH_001), ("004", GRAPH_004), ("007", GRAPH_007)],
    )
    def test_baseline_scores_as_valid_ordering(self, task_num: str, graph: dict) -> None:
        result = validate_refactor_plan_markdown(_load(task_num), graph)
        assert result["score"] >= 0.85, (
            f"refactor-orch-{task_num} baseline scored {result['score']} "
            f"(<0.85): {result['detail']}"
        )

    def test_pipeline_matches_manual_composition(self) -> None:
        # validate_refactor_plan_markdown must be equivalent to composing
        # extract_proposed_order -> resolve_tokens_to_graph -> validate_topological_order.
        text = _load("001")
        tokens = extract_proposed_order(text)
        resolved = resolve_tokens_to_graph(tokens, GRAPH_001.keys())
        expected = validate_topological_order(resolved, GRAPH_001)
        actual = validate_refactor_plan_markdown(text, GRAPH_001)
        assert actual == expected


class TestExtractionRegressionSafety:
    """The extraction rewrite must not regress the original flat-list format."""

    def test_flat_numbered_list_still_works(self) -> None:
        text = """\
# Refactor Plan

## Ordering
1. etcd-io/etcd
2. kubernetes/kubernetes

## Risk Assessment
- etcd-io/etcd: low risk
"""
        tokens = extract_proposed_order(text)
        assert tokens == ["etcd-io/etcd", "kubernetes/kubernetes"]

    def test_step_subsections_dont_leak_inner_numbered_actions(self) -> None:
        # A "### Step N" block's own inner numbered action list (e.g. "1. Bump
        # all go.etcd.io/etcd/* require entries...") must not be mistaken for
        # additional top-level ordering entries.
        text = """\
## Execution Plan (Topologically Sorted)

### Step 1 — Verify upstream
**Repo:** `etcd-io/etcd`

### Step 2 — Update consumer
**Repo:** `kubernetes/kubernetes`

**Actions:**
1. Bump all go.etcd.io/etcd/* require entries
2. Audit storage backend

## Parallelization Summary
"""
        tokens = extract_proposed_order(text)
        assert tokens == ["etcd-io/etcd", "kubernetes/kubernetes"]

    def test_no_ordering_section_returns_empty(self) -> None:
        assert extract_proposed_order("# Plan\n\nNo ordering here.\n") == []
