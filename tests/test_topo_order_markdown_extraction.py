"""Tests for REFACTOR_PLAN.md ordering extraction (EnterpriseBench-e1eq).

check_topo_order.sh's original extraction regex assumed the agent's proposed
ordering is always a flat "1. reponame" markdown list. Real completed runs
instead use "### Step N — <description>" headings (with the actual repo
named on a separate "**Repo:** `<repo>`" line), plain "Step N — <repo>"
lines, or "### Phase A — <repo>: <description>" lettered headings (with
"**Step N**" bolded sub-lines), and reference repos by narrative module
path ("go.etcd.io/etcd") or punctuation variant ("next.js" vs "nextjs")
rather than the literal "org/repo" dependency-graph key ("etcd-io/etcd").

These tests use real completed baseline runs
(results/rerun_pt0n/refactor-orch-{001,004,007}/baseline/REFACTOR_PLAN.md and
results/runs/{refactor-orch-005,refactor-orch-006,refactor-orch-008,
refactor-orchestration-tri-babel-001,refactor-orchestration-tri-spring-001}/
baseline/agent_trace.jsonl, copied into tests/fixtures/) that previously
scored 0.0 due to this mismatch.

006 and 005 name their per-repo detail inside markdown table cells nested
under a Phase/Step heading (e.g. a "Wave 1" table listing individual
staging-repo names) rather than in the heading text or a "**Repo:**" field.
Extracting table-cell identifiers is a separate, unscoped enhancement — see
EnterpriseBench-e1eq notes — so those two still score 0.0 here. That is the
real, current behavior, not a regression: before this fix they also scored
0.0, for the more severe reason that extraction found nothing at all.
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
GRAPH_008 = {
    "grpc-ecosystem/go-grpc-middleware": [],
    "etcd-io/etcd": ["grpc-ecosystem/go-grpc-middleware"],
    "kubernetes/kubernetes": [
        "etcd-io/etcd",
        "grpc-ecosystem/go-grpc-middleware",
    ],
}
GRAPH_006 = {
    "build-infra": [],
    "k8s.io/apimachinery": ["build-infra"],
    "k8s.io/api": ["build-infra", "k8s.io/apimachinery"],
    "k8s.io/client-go": ["build-infra", "k8s.io/apimachinery", "k8s.io/api"],
    "k8s.io/apiserver": [
        "build-infra",
        "k8s.io/apimachinery",
        "k8s.io/api",
        "k8s.io/client-go",
    ],
    "distroless-images": ["build-infra"],
    "e2e-infra": ["build-infra", "distroless-images"],
}
GRAPH_005 = {
    "@babel/core": [],
    "@babel/plugin-transform-react-compat": ["@babel/core"],
    "@babel/plugin-transform-react-source": ["@babel/core"],
    "@babel/plugin-transform-react-self": ["@babel/core"],
    "@babel/plugin-transform-property-mutators": ["@babel/core"],
    "@babel/preset-react": [
        "@babel/core",
        "@babel/plugin-transform-react-compat",
        "@babel/plugin-transform-react-source",
        "@babel/plugin-transform-react-self",
    ],
    "@babel/preset-env": ["@babel/core", "@babel/plugin-transform-property-mutators"],
}
# NOT the task's ground truth, and deliberately not synced to it. This is a
# fixture for the markdown-extraction regression test below, which replays a real
# recorded baseline REFACTOR_PLAN.md written against these package names; the
# graph has to keep them for that replay to mean anything. The task's real graph
# is @babel/standalone -> four deletions: three of the plugin names above DO NOT
# EXIST at babel@v7.25.0 (they are PR #17620 title shorthand for the real
# -react-jsx-compat/-jsx-self/-jsx-source packages), @babel/core is a
# peerDependency and carries no build-order edge, and neither preset depends on
# any removal target — so the graph below is the fabricated diamond the task was
# rebuilt away from. Do not copy it back into
# benchmarks/technical_debt/refactor-orchestration-005/ground_truth.json — see
# its _premise_correction (EnterpriseBench-jn73.2.7.3.1.2).
# NOT the task's ground truth, and deliberately not synced to it. This is a
# fixture for the markdown-extraction regression tests below, which replay a real
# recorded baseline REFACTOR_PLAN.md that names all three repos; the graph has to
# keep all three keys for that replay to mean anything. The task's real graph is
# a single edge, babel -> next.js: webpack v5.88.2 parses with acorn ^8.7.1 and
# declares no babel dependency, so the webpack edges below are the fabricated
# chain the task was rebuilt away from. Do not copy this graph back into
# benchmarks/technical_debt/refactor-orchestration-tri-babel-001/ground_truth.json
# — see its _premise_correction (EnterpriseBench-jn73.2.7.3.1.2).
GRAPH_TRI_BABEL_001 = {
    "babel/babel": [],
    "webpack/webpack": ["babel/babel"],
    "vercel/next.js": ["babel/babel", "webpack/webpack"],
}
GRAPH_TRI_SPRING_001 = {
    "spring-projects/spring-framework": [],
    "spring-projects/spring-kafka": ["spring-projects/spring-framework"],
    "spring-projects/spring-boot": [
        "spring-projects/spring-framework",
        "spring-projects/spring-kafka",
    ],
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

    def test_008_lettered_phase_headings_with_bolded_step(self) -> None:
        # "### Phase A — <repo>: <description>" headings, each followed by a
        # "**Step N** — ..." bolded (not heading) line. Both match the
        # broadened _STEP_LINE_RE; the Phase-level "<repo>:" token is the
        # signal, the Step-level narrative tokens are noise that fails to
        # resolve later.
        tokens = extract_proposed_order(_load("008"))
        assert tokens == [
            "etcd",
            "Add",
            "etcd",
            "Replace",
            "etcd",
            "Reimplement",
            "etcd",
            "Remove",
            "Kubernetes",
            "Bump",
            "Kubernetes",
            "Remove",
        ]

    def test_006_phase_and_bolded_step_headings_no_repo_field(self) -> None:
        # "### Phase N — <description>" headings with "**Step N — ...**"
        # bolded sub-lines; the per-repo detail lives in a markdown table
        # nested under each Step, which extraction does not parse (see
        # module docstring). Only the Phase 1 heading text ("Build
        # Infrastructure") yields a token that later resolves.
        tokens = extract_proposed_order(_load("006"))
        assert tokens[0] == "Build"
        assert "Wave" in tokens  # wave-table steps degrade to this placeholder

    def test_005_step_headings_with_table_no_repo_field(self) -> None:
        # "### Step N — <action description>" headings whose actual package
        # names live in a markdown table under each step, not the heading
        # text or a "**Repo:**" field — same table-cell gap as 006.
        tokens = extract_proposed_order(_load("005"))
        assert tokens == ["Remove", "Remove", "Remove", "Update", "Update"]

    def test_tri_babel_001_plain_colon_step_lines(self) -> None:
        # "Step N: <repo>     (<narrative note>)" plain lines with a colon
        # separator instead of an em-dash.
        tokens = extract_proposed_order(_load("tri-babel-001"))
        assert tokens == ["babel", "webpack", "nextjs"]

    def test_tri_spring_001_step_headings_repo_in_heading_text(self) -> None:
        # "### Step N — <repo> (<parenthetical>)" headings name the repo
        # directly in the heading text, no separate "**Repo:**" field needed.
        tokens = extract_proposed_order(_load("tri-spring-001"))
        assert tokens == ["spring-framework", "spring-kafka", "spring-boot"]


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

    def test_008_resolves_via_last_segment_dropping_unmatched_noise(self) -> None:
        tokens = extract_proposed_order(_load("008"))
        resolved = resolve_tokens_to_graph(tokens, GRAPH_008.keys())
        # go-grpc-middleware is never named as its own Phase, so it's
        # correctly absent rather than falsely matched.
        assert resolved == ["etcd-io/etcd", "kubernetes/kubernetes"]

    def test_tri_babel_001_resolves_via_punctuation_stripped_match(self) -> None:
        # "nextjs" only resolves to "vercel/next.js" once matching strips
        # the "." before comparing last-path-segments.
        tokens = extract_proposed_order(_load("tri-babel-001"))
        resolved = resolve_tokens_to_graph(tokens, GRAPH_TRI_BABEL_001.keys())
        assert resolved == ["babel/babel", "webpack/webpack", "vercel/next.js"]

    def test_tri_spring_001_resolves_to_three_graph_keys_in_order(self) -> None:
        tokens = extract_proposed_order(_load("tri-spring-001"))
        resolved = resolve_tokens_to_graph(tokens, GRAPH_TRI_SPRING_001.keys())
        assert resolved == [
            "spring-projects/spring-framework",
            "spring-projects/spring-kafka",
            "spring-projects/spring-boot",
        ]

    def test_006_resolves_build_infra_via_substring_fallback(self) -> None:
        # "Build" (Phase 1's heading text) only resolves to "build-infra" via
        # the substring fallback; none of the staging repos named inside the
        # Phase 3 wave tables resolve (table cells aren't extracted).
        tokens = extract_proposed_order(_load("006"))
        resolved = resolve_tokens_to_graph(tokens, GRAPH_006.keys())
        assert resolved == ["build-infra"]

    def test_005_resolves_nothing_table_cells_not_extracted(self) -> None:
        tokens = extract_proposed_order(_load("005"))
        resolved = resolve_tokens_to_graph(tokens, GRAPH_005.keys())
        assert resolved == []


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

    @pytest.mark.parametrize(
        "task_num,graph",
        [("tri-babel-001", GRAPH_TRI_BABEL_001), ("tri-spring-001", GRAPH_TRI_SPRING_001)],
    )
    def test_fully_covered_baseline_scores_as_valid_ordering(
        self, task_num: str, graph: dict
    ) -> None:
        result = validate_refactor_plan_markdown(_load(task_num), graph)
        assert result["score"] >= 0.85, (
            f"refactor-orch-{task_num} baseline scored {result['score']} "
            f"(<0.85): {result['detail']}"
        )

    def test_008_scores_partial_credit_not_zero(self) -> None:
        # Was "No numbered ordering found in plan" (0.0) before the Phase/
        # bold fix; now correctly orders etcd before kubernetes but is
        # penalized for the never-named go-grpc-middleware dependency.
        result = validate_refactor_plan_markdown(_load("008"), GRAPH_008)
        assert result["score"] == pytest.approx(0.2222, abs=1e-4)

    @pytest.mark.parametrize("task_num,graph", [("006", GRAPH_006), ("005", GRAPH_005)])
    def test_table_cell_baseline_still_scores_zero(self, task_num: str, graph: dict) -> None:
        # Known limitation (module docstring): per-repo identifiers live in
        # markdown table cells nested under a Step/Phase, which extraction
        # doesn't parse. Locks in current honest behavior rather than a
        # silent regression back to a crash or a false positive.
        result = validate_refactor_plan_markdown(_load(task_num), graph)
        assert result["score"] == 0.0

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
