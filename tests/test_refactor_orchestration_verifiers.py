"""Verification tests for refactor-orchestration task checkpoint scripts.

For each task, tests 3 tiers:
  (a) Ground truth answer -> score >=0.85
  (b) Empty answer -> score <=0.10
  (c) Partial answer (correct repos, wrong ordering) -> 0.15 <= score <= 0.75

Also tests:
  - Topological verifier accepts alternative valid orderings
  - Topological verifier rejects reversed orderings
  - All verifier scripts exist and are executable

Uses the validate_topological_order function directly for topo tests,
and bash verifier scripts for repo_set checks.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

BENCHMARKS_DIR = Path(__file__).parent.parent / "benchmarks" / "technical_debt"


@dataclass(frozen=True)
class RefactorTaskSpec:
    """Spec for testing one refactor orchestration task's verifiers."""

    task_num: str
    # GT: ordered list of repos as they appear in ground truth
    gt_order: list[str]
    # Dependency graph from ground_truth.json
    dep_graph: dict[str, list[str]]
    # GT answer content — a REFACTOR_PLAN.md the agent would write
    gt_answer: str
    # Partial answer — correct repos, wrong ordering
    partial_answer: str
    # Alternative valid ordering (if any)
    alt_order: list[str] = field(default_factory=list)
    # Repos to grep for in check_repo_set.sh
    repo_keywords: list[str] = field(default_factory=list)


TASKS: list[RefactorTaskSpec] = [
    RefactorTaskSpec(
        task_num="001",
        gt_order=["etcd-io/etcd", "kubernetes/kubernetes"],
        dep_graph={
            "etcd-io/etcd": [],
            "kubernetes/kubernetes": ["etcd-io/etcd"],
        },
        repo_keywords=["etcd", "kubernetes"],
        gt_answer="""\
# Refactor Plan

## Dependency Graph
- kubernetes/kubernetes depends on etcd-io/etcd

## Ordering
1. etcd-io/etcd
2. kubernetes/kubernetes

## Parallelization
No parallelizable steps — strict linear chain.

## Risk Assessment
- etcd-io/etcd: Low risk — upstream release, no breaking changes
- kubernetes/kubernetes: Medium risk — large dependency tree update
""",
        partial_answer="""\
# Refactor Plan

## Ordering
1. kubernetes/kubernetes
2. etcd-io/etcd

## Notes
Both repos need updates for etcd 3.6.
""",
    ),
    RefactorTaskSpec(
        task_num="002",
        gt_order=["spf13/cobra", "kubernetes/kubernetes"],
        dep_graph={
            "spf13/cobra": [],
            "kubernetes/kubernetes": ["spf13/cobra"],
        },
        repo_keywords=["cobra", "kubernetes"],
        gt_answer="""\
# Refactor Plan

## Dependency Graph
- kubernetes depends on spf13/cobra

## Ordering
1. spf13/cobra
2. kubernetes/kubernetes

## Parallelization
No parallelizable steps.

## Risk Assessment
- spf13/cobra: Low risk — upstream release
- kubernetes/kubernetes: Low risk — CLI framework bump, well-tested
""",
        partial_answer="""\
# Refactor Plan

## Ordering
1. kubernetes/kubernetes
2. spf13/cobra

## Notes
Cobra bump for kubectl.
""",
    ),
    RefactorTaskSpec(
        task_num="003",
        gt_order=["grpc/grpc-go", "etcd-io/etcd", "kubernetes/kubernetes"],
        dep_graph={
            "grpc/grpc-go": [],
            "etcd-io/etcd": ["grpc/grpc-go"],
            "kubernetes/kubernetes": ["grpc/grpc-go", "etcd-io/etcd"],
        },
        repo_keywords=["grpc-go", "etcd", "kubernetes"],
        gt_answer="""\
# Refactor Plan

## Dependency Graph
- etcd-io/etcd depends on grpc/grpc-go
- kubernetes/kubernetes depends on grpc/grpc-go and etcd-io/etcd

## Ordering
1. grpc/grpc-go
2. etcd-io/etcd
3. kubernetes/kubernetes

## Parallelization
No parallelizable steps — linear chain.

## Risk Assessment
- grpc/grpc-go: Breaking interface change in ServiceRegistrar
- etcd-io/etcd: Must fix mock server implementations
- kubernetes/kubernetes: Must update vendor and fix test mocks
""",
        partial_answer="""\
# Refactor Plan

## Ordering
1. kubernetes/kubernetes
2. etcd-io/etcd
3. grpc/grpc-go

## Notes
grpc-go v1.72.1 update needed across the stack.
""",
    ),
    RefactorTaskSpec(
        task_num="004",
        gt_order=["protocolbuffers/protobuf-go", "grpc/grpc-go", "etcd-io/etcd"],
        dep_graph={
            "protocolbuffers/protobuf-go": [],
            "grpc/grpc-go": ["protocolbuffers/protobuf-go"],
            "etcd-io/etcd": ["grpc/grpc-go", "protocolbuffers/protobuf-go"],
        },
        repo_keywords=["protobuf", "grpc-go", "etcd"],
        gt_answer="""\
# Refactor Plan

## Dependency Graph
- grpc/grpc-go depends on protocolbuffers/protobuf-go
- etcd-io/etcd depends on grpc/grpc-go and protocolbuffers/protobuf-go

## Ordering
1. protocolbuffers/protobuf-go
2. grpc/grpc-go
3. etcd-io/etcd

## Import Path Changes
- grpc-go: github.com/golang/protobuf -> google.golang.org/protobuf
- etcd: update imports after grpc-go migration

## Parallelization
No parallelizable steps.

## Risk Assessment
- protobuf-go: Already released, no changes needed
- grpc-go: Major import path migration, high risk
- etcd-io/etcd: Must adapt to new grpc-go protobuf imports
""",
        partial_answer="""\
# Refactor Plan

## Ordering
1. etcd-io/etcd
2. grpc/grpc-go
3. protocolbuffers/protobuf-go

## Notes
Protobuf v1 to v2 import migration.
""",
    ),
    RefactorTaskSpec(
        task_num="005",
        gt_order=[
            "@babel/core",
            "@babel/plugin-transform-react-compat",
            "@babel/plugin-transform-react-source",
            "@babel/plugin-transform-react-self",
            "@babel/plugin-transform-property-mutators",
            "@babel/preset-react",
            "@babel/preset-env",
        ],
        dep_graph={
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
        },
        repo_keywords=["preset-env", "preset-react", "plugin-transform-react", "plugin-transform-property-mutators", "@babel/core"],
        alt_order=[
            "@babel/core",
            "@babel/plugin-transform-property-mutators",
            "@babel/plugin-transform-react-compat",
            "@babel/plugin-transform-react-source",
            "@babel/plugin-transform-react-self",
            "@babel/preset-env",
            "@babel/preset-react",
        ],
        gt_answer="""\
# Refactor Plan

## Dependency Graph
- All plugins depend on @babel/core
- @babel/preset-react depends on plugin-transform-react-{compat,source,self}
- @babel/preset-env depends on plugin-transform-property-mutators

## Ordering
1. @babel/core
2. @babel/plugin-transform-react-compat
3. @babel/plugin-transform-react-source
4. @babel/plugin-transform-react-self
5. @babel/plugin-transform-property-mutators
6. @babel/preset-react
7. @babel/preset-env

## Parallelization
Parallel: @babel/plugin-transform-react-compat, @babel/plugin-transform-react-source, @babel/plugin-transform-react-self, @babel/plugin-transform-property-mutators (all only depend on @babel/core).
Parallel: @babel/preset-react, @babel/preset-env (independent presets).

## Risk Assessment
- @babel/core: Breaking change foundation, must be updated first
- Plugins: Removal, low risk individually
- Presets: Must remove references to deleted plugins
""",
        partial_answer="""\
# Refactor Plan

## Ordering
1. @babel/core
2. @babel/preset-react
3. @babel/preset-env
4. @babel/plugin-transform-react-compat

## Notes
Babel 8 plugin removal. Some plugins need removing.
""",
    ),
    RefactorTaskSpec(
        task_num="006",
        gt_order=[
            "build-infra",
            "k8s.io/apimachinery",
            "k8s.io/api",
            "k8s.io/client-go",
            "k8s.io/apiserver",
            "distroless-images",
            "e2e-infra",
        ],
        dep_graph={
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
        },
        repo_keywords=["apimachinery", "client-go", "apiserver", "distroless", "api"],
        alt_order=[
            "build-infra",
            "distroless-images",
            "k8s.io/apimachinery",
            "e2e-infra",
            "k8s.io/api",
            "k8s.io/client-go",
            "k8s.io/apiserver",
        ],
        gt_answer="""\
# Refactor Plan

## Dependency Graph
- k8s.io/apimachinery depends on build-infra
- k8s.io/api depends on build-infra, k8s.io/apimachinery
- k8s.io/client-go depends on build-infra, k8s.io/apimachinery, k8s.io/api
- k8s.io/apiserver depends on all above
- distroless-images depends on build-infra
- e2e-infra depends on build-infra, distroless-images

## Ordering
1. build-infra
2. k8s.io/apimachinery
3. k8s.io/api
4. k8s.io/client-go
5. k8s.io/apiserver
6. distroless-images
7. e2e-infra

## Parallelization
These steps can run concurrently: k8s.io/apimachinery, distroless-images
These steps can run concurrently: k8s.io/client-go, e2e-infra

## Risk Assessment
- build-infra: Foundation — must succeed first
- k8s.io/apimachinery: Core types, high blast radius
- distroless-images: Independent rebuild, low risk
""",
        partial_answer="""\
# Refactor Plan

## Ordering
1. build-infra
2. k8s.io/client-go
3. k8s.io/apimachinery
4. k8s.io/api
5. k8s.io/apiserver

## Notes
Go 1.26 update for Kubernetes staging repos.
""",
    ),
    RefactorTaskSpec(
        task_num="007",
        gt_order=["grpc/grpc-go", "etcd-io/etcd", "kubernetes/kubernetes"],
        dep_graph={
            "grpc/grpc-go": [],
            "etcd-io/etcd": ["grpc/grpc-go"],
            "kubernetes/kubernetes": ["grpc/grpc-go", "etcd-io/etcd"],
        },
        repo_keywords=["grpc-go", "etcd", "kubernetes"],
        gt_answer="""\
# Refactor Plan

## Dependency Graph
- etcd-io/etcd depends on grpc/grpc-go
- kubernetes/kubernetes depends on grpc/grpc-go and etcd-io/etcd

## Ordering
1. grpc/grpc-go
2. etcd-io/etcd
3. kubernetes/kubernetes

## API Migration Details
- grpc-go: grpc.Dial/DialContext deprecated, use grpc.NewClient
- etcd: Replace Dial in clientv3, preserve DialTimeout via health endpoint
- kubernetes: Update to new etcd client, update own grpc.Dial sites

## Parallelization
No parallelizable steps.

## Behavioral Differences
- NewClient is non-blocking by default (Dial was blocking)
- Health check endpoint replaces connection-time validation
""",
        partial_answer="""\
# Refactor Plan

## Ordering
1. kubernetes/kubernetes
2. etcd-io/etcd
3. grpc/grpc-go

## Notes
Dial -> NewClient migration.
""",
    ),
    RefactorTaskSpec(
        task_num="008",
        gt_order=[
            "grpc-ecosystem/go-grpc-middleware",
            "etcd-io/etcd",
            "kubernetes/kubernetes",
        ],
        dep_graph={
            "grpc-ecosystem/go-grpc-middleware": [],
            "etcd-io/etcd": ["grpc-ecosystem/go-grpc-middleware"],
            "kubernetes/kubernetes": [
                "etcd-io/etcd",
                "grpc-ecosystem/go-grpc-middleware",
            ],
        },
        repo_keywords=["go-grpc-middleware", "etcd", "kubernetes", "grpc-prometheus"],
        gt_answer="""\
# Refactor Plan

## Dependency Graph
- etcd-io/etcd depends on grpc-ecosystem/go-grpc-middleware
- kubernetes/kubernetes depends on etcd-io/etcd and go-grpc-middleware (via go-grpc-prometheus)

## Ordering
1. grpc-ecosystem/go-grpc-middleware
2. etcd-io/etcd
3. kubernetes/kubernetes

## Migration Strategy
- go-grpc-middleware: Archived, no changes needed (reference only)
- etcd: Migrate logging to v2, then remove v1 dependency entirely
- kubernetes: Drop go-grpc-prometheus, replace with OpenTelemetry gRPC metrics

## Parallelization
No parallelizable steps.

## Risk Assessment
- etcd: Two-step migration (v2 first, then full removal)
- kubernetes: Must replace metrics collection, not just drop
""",
        partial_answer="""\
# Refactor Plan

## Ordering
1. kubernetes/kubernetes
2. etcd-io/etcd

## Notes
Need to remove go-grpc-middleware dependency. grpc-prometheus also affected.
""",
    ),
]


# -- helpers ------------------------------------------------------------------


def _task_dir(task_num: str) -> Path:
    return BENCHMARKS_DIR / f"refactor-orchestration-{task_num}"


CHECKPOINT_NAMES = [
    "check_repo_set",
    "check_topo_order",
    "check_parallelism",
]

CHECKPOINT_WEIGHTS = (0.25, 0.45, 0.30)


def _run_verifier(
    task_num: str,
    checkpoint_name: str,
    workspace: Path,
) -> dict[str, Any]:
    """Run a checkpoint verifier script and return parsed JSON output."""
    script = _task_dir(task_num) / "checks" / f"{checkpoint_name}.sh"
    assert script.exists(), f"Verifier not found: {script}"

    env = os.environ.copy()
    env["WORKSPACE"] = str(workspace)
    env["TASK_DIR"] = str(_task_dir(task_num))
    env["TASK_ID"] = f"refactor-orch-{task_num}"

    result = subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(workspace),
        env=env,
    )
    stdout = result.stdout.strip()
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return {"score": 1.0 if result.returncode == 0 else 0.0, "raw": stdout, "stderr": result.stderr}


def _write_plan(workspace: Path, content: str) -> Path:
    """Write a REFACTOR_PLAN.md into the workspace root."""
    workspace.mkdir(parents=True, exist_ok=True)
    plan_path = workspace / "REFACTOR_PLAN.md"
    plan_path.write_text(content)
    return plan_path


def _weighted_score(
    results: list[dict[str, Any]],
    weights: tuple[float, ...] = CHECKPOINT_WEIGHTS,
) -> float:
    """Compute weighted score from checkpoint results."""
    total = 0.0
    for r, w in zip(results, weights):
        total += float(r.get("score", 0.0)) * w
    return total


# -- tests: 3 tiers per task -------------------------------------------------


class TestGroundTruthScoresHigh:
    """(a) Ground truth answer should score >=0.85."""

    @pytest.mark.parametrize("spec", TASKS, ids=[t.task_num for t in TASKS])
    def test_gt_answer_scores_high(self, tmp_path: Path, spec: RefactorTaskSpec) -> None:
        workspace = tmp_path / "workspace"
        _write_plan(workspace, spec.gt_answer)

        results = [
            _run_verifier(spec.task_num, cp, workspace)
            for cp in CHECKPOINT_NAMES
        ]
        total = _weighted_score(results)
        assert total >= 0.85, (
            f"Task {spec.task_num} GT scored {total:.2f} (<0.85). "
            f"Results: {results}"
        )


class TestEmptyAnswerScoresLow:
    """(b) Empty/missing answer should score <=0.10."""

    @pytest.mark.parametrize("spec", TASKS, ids=[t.task_num for t in TASKS])
    def test_empty_answer_scores_low(self, tmp_path: Path, spec: RefactorTaskSpec) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir(parents=True)
        # No REFACTOR_PLAN.md -- verifiers should return 0

        results = [
            _run_verifier(spec.task_num, cp, workspace)
            for cp in CHECKPOINT_NAMES
        ]
        total = _weighted_score(results)
        assert total <= 0.10, (
            f"Task {spec.task_num} empty scored {total:.2f} (>0.10). "
            f"Results: {results}"
        )


class TestPartialAnswerScoresMid:
    """(c) Partial answer (correct repos, wrong ordering) scores 0.15-0.75."""

    @pytest.mark.parametrize("spec", TASKS, ids=[t.task_num for t in TASKS])
    def test_partial_answer_scores_mid(self, tmp_path: Path, spec: RefactorTaskSpec) -> None:
        workspace = tmp_path / "workspace"
        _write_plan(workspace, spec.partial_answer)

        results = [
            _run_verifier(spec.task_num, cp, workspace)
            for cp in CHECKPOINT_NAMES
        ]
        total = _weighted_score(results)
        assert 0.15 <= total <= 0.75, (
            f"Task {spec.task_num} partial scored {total:.2f} (expected 0.15-0.75). "
            f"Results: {results}"
        )


# -- tests: topological ordering specific ------------------------------------


class TestTopoAcceptsAlternativeOrdering:
    """Topological verifier must accept alternative valid orderings."""

    @pytest.mark.parametrize(
        "spec",
        [s for s in TASKS if s.alt_order],
        ids=[s.task_num for s in TASKS if s.alt_order],
    )
    def test_alt_ordering_scores_high(self, spec: RefactorTaskSpec) -> None:
        from eb_verify.plugins.topological_order import validate_topological_order

        result = validate_topological_order(spec.alt_order, spec.dep_graph)
        assert result["score"] >= 0.85, (
            f"Task {spec.task_num} alt ordering scored {result['score']:.2f} (<0.85). "
            f"Alt order: {spec.alt_order}, Detail: {result['detail']}"
        )


class TestTopoRejectsReversedOrdering:
    """Topological verifier must reject reversed orderings."""

    @pytest.mark.parametrize("spec", TASKS, ids=[t.task_num for t in TASKS])
    def test_reversed_ordering_scores_low(self, spec: RefactorTaskSpec) -> None:
        from eb_verify.plugins.topological_order import validate_topological_order

        reversed_order = list(reversed(spec.gt_order))
        # Remove duplicates while preserving reverse order
        seen: set[str] = set()
        deduped: list[str] = []
        for r in reversed_order:
            if r not in seen:
                seen.add(r)
                deduped.append(r)

        result = validate_topological_order(deduped, spec.dep_graph)
        assert result["score"] <= 0.30, (
            f"Task {spec.task_num} reversed scored {result['score']:.2f} (>0.30). "
            f"Reversed: {deduped}, Detail: {result['detail']}"
        )


class TestTopoAcceptsGTOrdering:
    """Ground truth ordering scores high via topological verifier directly."""

    @pytest.mark.parametrize("spec", TASKS, ids=[t.task_num for t in TASKS])
    def test_gt_ordering_scores_high(self, spec: RefactorTaskSpec) -> None:
        from eb_verify.plugins.topological_order import validate_topological_order

        # Deduplicate GT order (task 008 has duplicate etcd entries)
        seen: set[str] = set()
        deduped: list[str] = []
        for r in spec.gt_order:
            if r not in seen:
                seen.add(r)
                deduped.append(r)

        result = validate_topological_order(deduped, spec.dep_graph)
        assert result["score"] >= 0.85, (
            f"Task {spec.task_num} GT ordering scored {result['score']:.2f} (<0.85). "
            f"Order: {deduped}, Detail: {result['detail']}"
        )


# -- tests: structural -------------------------------------------------------


class TestVerifierScriptsExist:
    """All 8 tasks have all 3 checkpoint verifier scripts."""

    @pytest.mark.parametrize("task_num", [f"{i:03d}" for i in range(1, 9)])
    def test_all_verifiers_present(self, task_num: str) -> None:
        task_dir = _task_dir(task_num)
        for cp in CHECKPOINT_NAMES:
            script = task_dir / "checks" / f"{cp}.sh"
            assert script.exists(), f"Missing: {script}"
            assert os.access(script, os.X_OK), f"Not executable: {script}"


class TestGroundTruthFilesValid:
    """All 8 tasks have valid ground_truth.json with required fields."""

    @pytest.mark.parametrize("task_num", [f"{i:03d}" for i in range(1, 9)])
    def test_ground_truth_valid(self, task_num: str) -> None:
        gt_path = _task_dir(task_num) / "ground_truth.json"
        assert gt_path.exists(), f"Missing: {gt_path}"

        with open(gt_path) as f:
            gt = json.load(f)

        assert "dependency_graph" in gt, "Missing dependency_graph"
        assert "merge_order" in gt, "Missing merge_order"
        assert "repos" in gt, "Missing repos"
        assert "difficulty" in gt, "Missing difficulty"
        assert isinstance(gt["dependency_graph"], dict)
        assert len(gt["dependency_graph"]) >= 2
