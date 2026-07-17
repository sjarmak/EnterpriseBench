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
    # Re-scoped 2026-07-16: the old spec carried the fabricated diamond
    # (@babel/core -> four plugins -> two presets). Three of those plugin names
    # DO NOT EXIST at babel@v7.25.0 -- they are PR #17620 title shorthand for the
    # real -react-jsx-* packages -- and neither preset depends on any removal
    # target. @babel/standalone is the sole workspace consumer, so its
    # reference-drop must land before the deletions. Synced to
    # benchmarks/technical_debt/refactor-orchestration-005/ground_truth.json;
    # see its _premise_correction (EnterpriseBench-jn73.2.7.3.1.2).
    RefactorTaskSpec(
        task_num="005",
        gt_order=[
            "@babel/standalone",
            "@babel/plugin-transform-react-jsx-compat",
            "@babel/plugin-transform-react-jsx-self",
            "@babel/plugin-transform-react-jsx-source",
            "@babel/plugin-transform-property-mutators",
        ],
        dep_graph={
            "@babel/standalone": [],
            "@babel/plugin-transform-react-jsx-compat": ["@babel/standalone"],
            "@babel/plugin-transform-react-jsx-self": ["@babel/standalone"],
            "@babel/plugin-transform-react-jsx-source": ["@babel/standalone"],
            "@babel/plugin-transform-property-mutators": ["@babel/standalone"],
        },
        repo_keywords=["standalone", "plugin-transform-react-jsx", "plugin-transform-property-mutators"],
        alt_order=[
            "@babel/standalone",
            "@babel/plugin-transform-property-mutators",
            "@babel/plugin-transform-react-jsx-source",
            "@babel/plugin-transform-react-jsx-compat",
            "@babel/plugin-transform-react-jsx-self",
        ],
        gt_answer="""\
# Babel 8 Plugin Removal Cascade — Refactor Plan

## Order

1. `@babel/standalone` — drop the four plugins from devDependencies, remove their
   imports and registry entries from `src/generated/plugins.ts`, delete their
   entries from `scripts/pluginConfig.json`, drop the four project references
   from `tsconfig.json`
2. `@babel/plugin-transform-react-jsx-compat` — delete package
3. `@babel/plugin-transform-react-jsx-self` — delete package
4. `@babel/plugin-transform-react-jsx-source` — delete package
5. `@babel/plugin-transform-property-mutators` — delete package

## Internal Dependency Graph

Exactly one workspace package references the removal targets:

- `@babel/standalone` declares all four under devDependencies in
  `packages/babel-standalone/package.json` as `"workspace:^"`, imports them in
  `src/generated/plugins.ts`, and registers them in `scripts/pluginConfig.json`.

The tracking notes are wrong about the diamond:

- `@babel/preset-env` is not affected — its dependencies do not include `plugin-transform-property-mutators`.
- `@babel/preset-react` is not affected — it depends on `plugin-transform-react-jsx`, `plugin-transform-react-jsx-development`, `plugin-transform-react-display-name` and `plugin-transform-react-pure-annotations`, none of which are removal targets.
- `@babel/core` requires no change — it is a `peerDependency` of the plugins, not a dependent.

## Parallelization

Once `@babel/standalone` has landed, the four deletions are mutually independent
and can proceed in parallel:
- `@babel/plugin-transform-react-jsx-compat`
- `@babel/plugin-transform-react-jsx-self`
- `@babel/plugin-transform-react-jsx-source`
- `@babel/plugin-transform-property-mutators`

## Breaking Change Impact
`@babel/standalone` drops four names from its public plugin registry.
""",
        # Correct scope and evidence, wrong ordering: the deletions are scheduled
        # before the standalone reference-drop they depend on, which breaks the
        # build mid-cascade. identify_repos and parallelism still pay.
        partial_answer="""\
# Babel 8 Plugin Removal Cascade — Refactor Plan

## Order

1. `@babel/plugin-transform-react-jsx-compat` — delete package
2. `@babel/plugin-transform-react-jsx-self` — delete package
3. `@babel/plugin-transform-react-jsx-source` — delete package
4. `@babel/plugin-transform-property-mutators` — delete package
5. `@babel/standalone` — drop the four plugins from devDependencies afterwards

## Internal Dependency Graph

- `@babel/standalone` declares all four under devDependencies in
  `packages/babel-standalone/package.json`.
- `@babel/preset-env` is not affected — no dependency on property-mutators.
- `@babel/preset-react` is not affected — it depends on jsx-development, not the removal targets.

## Parallelization

The four deletions are independent and can proceed in parallel:
- `@babel/plugin-transform-react-jsx-compat`
- `@babel/plugin-transform-react-jsx-self`
- `@babel/plugin-transform-react-jsx-source`
- `@babel/plugin-transform-property-mutators`
""",
    ),
    # Re-scoped 2026-07-16: the old spec carried a four-deep staging cascade
    # rooted at "build-infra", with "distroless-images" and "e2e-infra". Three of
    # those seven nodes DO NOT EXIST in the checkout, and a Go toolchain bump
    # touches no staging repo at all (PR #137080 changed seven files, none under
    # staging/src/). The real graph is the one the repo declares about itself:
    # build/dependencies.yaml carries a version plus a refPaths list per entry.
    # Synced to benchmarks/technical_debt/refactor-orchestration-006/ground_truth.json;
    # see its _premise_correction (EnterpriseBench-jn73.2.7.3.1.2).
    RefactorTaskSpec(
        task_num="006",
        gt_order=[
            "build/dependencies.yaml",
            ".go-version",
            "build/build-image/cross/VERSION",
            "staging/publishing/rules.yaml",
            "hack/lib/golang.sh",
            "build/common.sh",
            "test/utils/image/manifest.go",
        ],
        dep_graph={
            "build/dependencies.yaml": [],
            ".go-version": ["build/dependencies.yaml"],
            "build/build-image/cross/VERSION": ["build/dependencies.yaml"],
            "staging/publishing/rules.yaml": ["build/dependencies.yaml"],
            "hack/lib/golang.sh": ["build/dependencies.yaml"],
            "build/common.sh": ["build/dependencies.yaml"],
            "test/utils/image/manifest.go": ["build/dependencies.yaml"],
        },
        repo_keywords=["dependencies.yaml", "go-version", "rules.yaml", "golang.sh", "common.sh"],
        alt_order=[
            "build/dependencies.yaml",
            "build/common.sh",
            "test/utils/image/manifest.go",
            "hack/lib/golang.sh",
            "staging/publishing/rules.yaml",
            "build/build-image/cross/VERSION",
            ".go-version",
        ],
        gt_answer="""\
# Go 1.26.0 Toolchain Update — Refactor Plan

## Order

1. `build/dependencies.yaml` — bump the version fields: "golang: upstream version" 1.24.6 -> 1.26.0, "golang: 1.<major>" 1.24 -> 1.26, kube-cross, go-runner and distroless-iptables (v0.7.8 -> v0.9.0)
2. `.go-version` — 1.24.6 -> 1.26.0
3. `build/build-image/cross/VERSION` — v1.34.0-go1.24.6-bullseye.0 -> the go1.26.0 kube-cross tag
4. `staging/publishing/rules.yaml` — default-go-version: 1.24.6 -> 1.26.0
5. `hack/lib/golang.sh` — minimum_go_version=go1.24 -> go1.26
6. `build/common.sh` — __default_go_runner_version and __default_distroless_iptables_version
7. `test/utils/image/manifest.go` — configs[DistrolessIptables] v0.7.8 -> v0.9.0

## Dependency Graph

`build/dependencies.yaml` is the source of truth. Each entry carries a `version`
plus a `refPaths` list naming every file that must be kept in sync with it:

- "golang: upstream version" (1.24.6) refPaths: `.go-version`, `build/build-image/cross/VERSION`, `staging/publishing/rules.yaml`
- "golang: 1.<major>" (1.24) refPaths: `build/build-image/cross/VERSION`, `hack/lib/golang.sh`
- "registry.k8s.io/kube-cross: dependents" refPaths: `build/build-image/cross/VERSION`
- "registry.k8s.io/distroless-iptables: dependents" (v0.7.8) refPaths: `build/common.sh`, `test/utils/image/manifest.go`
- "registry.k8s.io/go-runner: dependents" refPaths: `build/common.sh`

The union of those refPaths plus the manifest itself is the whole set: seven files.

The release notes are wrong about the staging cascade:

- `k8s.io/client-go` is not affected — a toolchain bump touches no file under staging/src/; its go.mod declares `go 1.24.0` before and after, which is the language version, not the toolchain.
- `k8s.io/apimachinery` is likewise untouched, so the client-go -> apimachinery module edge carries no ordering constraint here.
- All 31 staging repos are handled centrally by one line, `staging/publishing/rules.yaml:default-go-version`.
- `build-infra`, `distroless-images` and `e2e-infra` do not exist in this checkout.

## Parallelization

Once `build/dependencies.yaml` is bumped, its six refPath targets are mutually
independent leaves and can all land together:
- `.go-version`
- `build/build-image/cross/VERSION`
- `staging/publishing/rules.yaml`
- `hack/lib/golang.sh`
- `build/common.sh`
- `test/utils/image/manifest.go`

## Risk Assessment
The referenced images must already be published to registry.k8s.io.
""",
        # Correct scope and evidence, wrong ordering: the refPath targets are
        # scheduled before the declaring manifest they follow from.
        partial_answer="""\
# Go 1.26.0 Toolchain Update — Refactor Plan

## Order

1. `.go-version` — 1.24.6 -> 1.26.0
2. `staging/publishing/rules.yaml` — default-go-version
3. `build/common.sh` — image defaults
4. `build/dependencies.yaml` — bump the version fields afterwards

## Dependency Graph

`build/dependencies.yaml` declares the propagation set via refPaths.

- `k8s.io/client-go` is not affected — no staging/src/ file changes in a toolchain bump.
- `k8s.io/apimachinery` is untouched for the same reason.

## Parallelization

These are independent and can land together:
- `.go-version`
- `build/build-image/cross/VERSION`
- `staging/publishing/rules.yaml`
- `hack/lib/golang.sh`
- `build/common.sh`
- `test/utils/image/manifest.go`
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
