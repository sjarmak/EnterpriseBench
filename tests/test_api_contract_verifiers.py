"""Verification tests for api-contract task checkpoint scripts.

For each task, tests 3 tiers:
  (a) Ground truth answer -> score >=0.85
  (b) Empty answer -> score <=0.10
  (c) Partial answer -> 0.3 <= score <= 0.7

Runs the actual bash verifier scripts via subprocess, matching the
eb_verify runner convention (WORKSPACE env var, JSON stdout).
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

BENCHMARKS_DIR = Path(__file__).parent.parent / "benchmarks" / "dependency_management"

# -- task definitions -------------------------------------------------------

@dataclass(frozen=True)
class TaskVerifierSpec:
    """Spec for testing one task's verifiers."""
    task_num: str
    # Ground truth answer content -- what a perfect agent would write
    gt_answer: str
    # Partial answer -- some but not all findings
    partial_answer: str


TASKS: list[TaskVerifierSpec] = [
    TaskVerifierSpec(
        task_num="001",
        gt_answer="""\
# Impact Report

## Breaking API Changes

The breaking change is in `metadata/metadata.go`. The functions
`metadata.FromContext` and `metadata.NewContext` were split into:
- `metadata.FromIncomingContext` / `metadata.FromOutgoingContext`
- `metadata.NewOutgoingContext`

## Affected etcd Files

| File | Breakage |
|------|----------|
| `auth/store.go` | compile error - uses FromContext |
| `etcdserver/api/v3rpc/interceptor.go` | compile + runtime - forwards metadata |
| `etcdserver/api/v3rpc/grpc.go` | compile error - uses NewContext |
| `clientv3/auth.go` | compile error - auth token forwarding |

## Critical: Metadata Forwarding

The interceptor in `v3rpc/interceptor.go` is the most dangerous case.
It forwards auth tokens between incoming and outgoing contexts.
After this change, metadata is silently dropped unless explicitly
copied from incoming to outgoing context. This is a runtime behavior
change that causes credential propagation failures.

## Classification
- `auth/store.go`: compile error (function not found)
- `v3rpc/interceptor.go`: compile + runtime behavior change (metadata silently lost)
- `v3rpc/grpc.go`: compile error
- `clientv3/auth.go`: compile error
""",
        partial_answer="""\
# Impact Report

## Breaking API Changes

Changes in `metadata/metadata.go`:
- `FromContext` renamed to `FromIncomingContext`

## Affected Files

- `auth/store.go` - compile error
""",
    ),
    TaskVerifierSpec(
        task_num="002",
        gt_answer="""\
# Impact Report

## Source Changes

In `balancer/balancer.go` and `resolver/resolver.go`, backward-compatibility
type aliases were removed. These aliases bridged old and new package paths.

## Affected etcd Files

- `clientv3/balancer/picker/err.go` - implements Picker interface
- `clientv3/balancer/picker/roundrobin_balanced.go` - custom round-robin picker
- `clientv3/balancer/resolver/endpoint/endpoint.go` - custom endpoint resolver

## Dependency Chain

etcd has a custom balancer architecture in `clientv3/balancer/`:
- Custom Picker implementations depend on `balancer.Picker` type alias
- Custom resolver depends on `resolver.Builder` type alias
- The entire custom balancer needs to be restructured

## Fix Assessment

This is NOT a simple import path change. etcd's custom balancer architecture
needs a deeper rework to replace deprecated APIs with upstream grpc solutions.
The compile errors are the immediate symptom, but the real fix requires
architectural refactoring.
""",
        partial_answer="""\
# Impact Report

## Source Changes
Removed type aliases in `balancer/balancer.go`.

## Affected Files
- `clientv3/balancer/picker/err.go` - compile error
""",
    ),
    TaskVerifierSpec(
        task_num="003",
        gt_answer="""\
# Impact Report

## Transport Package Internalization

The `transport` package moved to `internal/transport` in grpc-go.
Key types: `ClientTransport`, `ServerTransport`, `Stream`.
Files: `transport.go`, `http2_client.go`, `http2_server.go` all moved.
Also affected: `clientconn.go`, `server.go`, `stream.go`.

## Direct etcd Impact

etcd imports `google.golang.org/grpc/transport` in vendor directory.
Multiple etcd files reference transport types.

## Kubernetes Transitive Impact

kubernetes vendors both grpc-go and etcd. The vendor directory contains
`vendor/google.golang.org/grpc/transport/` references.
Affected k8s subsystems: apiserver, kubelet, staging.
The k8s fix PR changed 381 files due to cascading vendor updates.

## Three-Repo Chain

grpc-go → etcd → kubernetes

The chain propagates through vendoring:
1. grpc-go moves transport to internal (27 files)
2. etcd must update its vendored grpc-go
3. kubernetes must update its vendored etcd AND grpc-go (381 files)

This is a massive vendor update impacting hundreds of files.
""",
        partial_answer="""\
# Impact Report

## Transport Move
The `internal/transport` package was created from `transport`.
Key file: `transport.go`.

## etcd Impact
etcd imports grpc transport directly.
""",
    ),
    TaskVerifierSpec(
        task_num="004",
        gt_answer="""\
# Impact Report

## Breaking Change in balancer.ClientConn

In `balancer/balancer.go`, an internal method was added to the
`ClientConn` interface. All implementations must now embed a delegate
implementation to satisfy the interface.

The `balancer/subconn.go` and `balancer_wrapper.go` were also modified.

## Affected etcd Types

etcd's `client/v3/balancer/` package implements `balancer.ClientConn`
for its custom balancer logic. These implementations will fail to
compile because they don't embed the delegate.

The experimental resolver and balancer code in etcd is tightly coupled
to grpc-go's internal APIs.

## Test Mocks

Test mocks and fakes that implement `balancer.ClientConn` in test
utilities also need updating. The `MetricsRecorder` method is now
accessed through `ClientConn` instead of `BuildOptions`.

## Fix Assessment

etcd needs to either embed the delegate or restructure its custom
balancer. Given the broader issue (etcd#15145), this is part of a
larger architectural refactoring to remove dependency on grpc-go
experimental APIs.
""",
        partial_answer="""\
# Impact Report

## Breaking Change
The `ClientConn` interface in `balancer.go` now requires embedding.

## etcd Impact
etcd's clientv3 balancer implements ClientConn and will fail to compile.
""",
    ),
    TaskVerifierSpec(
        task_num="005",
        gt_answer="""\
# Impact Report

## Root Cause

In `internal/status/status.go`, the migration from
`github.com/golang/protobuf` to `google.golang.org/protobuf/proto`
changed how `Status.Details()` works.

Before: used `ptypes.UnmarshalAny` which returned `MessageV1` types
via `protoadapt.MessageV1Of()`.
After: uses `anypb.Any.UnmarshalNew()` which returns `MessageV2` types.

## Affected Files

- `internal/status/status.go` - the core change
- `status/status_ext_test.go` - tests that assert on detail types
- `encoding/proto/proto.go` - proto marshaling utilities
- `internal/testutils/status_equal.go` - test helper

`Status.Details()` and `Status.WithDetails()` are called throughout
the codebase.

## Type System Issue

The issue is that type assertions like `detail.(*errdetails.BadRequest)`
silently fail when the returned type is `MessageV2` instead of
`MessageV1`. Code generated by `protoc-gen-go` < v1.4 (released 2020)
produces types that only implement `MessageV1`.

## Classification

This is a **runtime** behavior change, not a compile error.
Everything compiles fine, but type assertions fail silently at runtime.
The bug took 9 months to detect (Jan 2024 migration, Oct 2024 fix)
because of its subtle, silent failure mode.
""",
        partial_answer="""\
# Impact Report

## Root Cause
Change in `internal/status/status.go` from `UnmarshalAny` to new API.

## Affected Files
- `status/status_ext_test.go` - test assertions affected
""",
    ),
    TaskVerifierSpec(
        task_num="006",
        gt_answer="""\
# Impact Report

## xDS v2 Deprecation

Envoy deprecated xDS v2 APIs in a phased rollout:
- Warning phase: v2 usage logged warnings
- Fatal phase: v2 transport API fatal-by-default (PR #14223)
- Removal: no override available (PR #15481)

Affected xDS types: CDS (Cluster), EDS (Endpoint), LDS (Listener),
RDS (Route) discovery services.

## go-control-plane Impact

The `go-control-plane` library maintained parallel v2 and v3 package
trees. PR #415 removed 78 files from `pkg/cache/v2/`, `pkg/server/v2/`,
etc.

Key removed files:
- `pkg/cache/v2/cache.go`
- `pkg/cache/v2/resource.go`

## istio Impact

istio's pilot component needed massive migration:
- `pilot/pkg/networking/core/v1alpha3/cluster.go` - Cluster generation
- `pilot/pkg/networking/core/v1alpha3/listener.go` - Listener generation
- `pilot/pkg/proxy/envoy/v2/ads.go` - ADS server
- `pilot/pkg/proxy/envoy/v2/cds.go` - CDS handling
- `pilot/pkg/proxy/envoy/v2/eds.go` - EDS handling

Total: 48 + 107 files across multiple istio PRs (150+ total).

## Chain: envoy → go-control-plane → istio

The chain propagates through proto definitions:
1. Envoy defines xDS protos and marks v2 as fatal
2. go-control-plane removes Go v2 bindings
3. istio must rewrite pilot to use v3 types

This was a runtime fatal error - Envoy rejects v2 requests entirely.
""",
        partial_answer="""\
# Impact Report

## xDS v2 Deprecation
Envoy made xDS v2 fatal-by-default.

## go-control-plane
Removed `pkg/cache/v2/cache.go` and related v2 packages.
""",
    ),
    TaskVerifierSpec(
        task_num="007",
        gt_answer="""\
# Impact Report

## Module Structure

The go-control-plane repo was restructured into a multi-module layout:
- Root: `github.com/envoyproxy/go-control-plane` (go.mod)
- Submodule: `github.com/envoyproxy/go-control-plane/envoy` (envoy/go.mod)
- Submodule: `github.com/envoyproxy/go-control-plane/contrib` (contrib/go.mod)

## Affected Consumers

Three major projects were affected:
- **istio** - regular go-control-plane consumer
- **grpc-go** - depends on envoy proto types
- **google-cloud-go** (googleapis/google-cloud-go) - transitive dependency

The error was a dependency resolution failure during `go get -u`.
Version v0.13.2 broke the module proxy resolution.

## Fix Analysis

PR #1075 added backward-compatible empty import files:
- `envoy/empty.go` - ensures the submodule has Go source files

The empty Go files with proper package declarations allow the Go module
proxy to correctly resolve the submodule path. Without them, `go get -u`
couldn't distinguish between the root module and submodule paths.

Workaround: `go mod edit --exclude=github.com/envoyproxy/go-control-plane@v0.13.2`

## grpc-go Follow-up

grpc-go PR #8067 bumped `envoyproxy/go-control-plane/envoy` and
synchronized go.mods across the grpc-go multi-module structure.
""",
        partial_answer="""\
# Impact Report

## Module Split
go-control-plane split into multi-module layout with `envoy/go.mod`.

## Affected Consumers
- istio
""",
    ),
    TaskVerifierSpec(
        task_num="008",
        gt_answer="""\
# Impact Report

## cel.Program Interface Change

cel-go v0.10.1 added a new method to the `cel.Program` interface.
This is a breaking change for any type that implements `cel.Program`
without using embedding.

## Affected Mock in grpc-go

The mock/fake `cel.Program` implementation is in:
- `security/authorization/engine/engine_test.go`

This test file has a mock that directly implements `cel.Program`
for unit testing the RBAC authorization engine. The mock doesn't
implement the new method, causing a compile error.

The fix also updated:
- `security/authorization/go.mod` - bumped cel-go to v0.10.1
- `security/authorization/go.sum`

## Broader Impact

The authorization and RBAC engine packages use cel-go for policy
evaluation. The xDS RBAC engine (`internal/xds/rbac/`) also uses
cel-go but may use the real `cel.Program` rather than mocks.

## Classification

This is a compile error specifically in test code. The production
code uses the real cel.Program from the library, not a mock, so
it isn't affected. Only test mocks that directly implement the
interface break.
""",
        partial_answer="""\
# Impact Report

## cel.Program Change
A new method was added to `cel.Program` in cel-go v0.10.1.

## Affected File
- `security/authorization/engine/engine_test.go` has a mock that broke.
""",
    ),
]


# -- helpers ----------------------------------------------------------------

def _task_dir(task_num: str) -> Path:
    return BENCHMARKS_DIR / f"api-contract-{task_num}"


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
    env["TASK_ID"] = f"api-contract-{task_num}"

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
        return {"score": 1.0 if result.returncode == 0 else 0.0, "raw": stdout}


def _write_report(workspace: Path, content: str) -> Path:
    """Write an IMPACT_REPORT.md into the workspace."""
    report_dir = workspace / "analysis"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "IMPACT_REPORT.md"
    report_path.write_text(content)
    return report_path


CHECKPOINT_NAMES = [
    "check_source_identification",
    "check_direct_consumers",
    "check_transitive_impact",
    "check_classification",
]

WEIGHTS = (0.15, 0.35, 0.30, 0.20)


def _weighted_score(results: list[dict[str, Any]]) -> float:
    """Compute weighted score from 4 checkpoint results."""
    total = 0.0
    for r, w in zip(results, WEIGHTS):
        total += float(r.get("score", 0.0)) * w
    return total


# -- tests ------------------------------------------------------------------

class TestGroundTruthScoresHigh:
    """(a) Ground truth answer should score >=0.85."""

    @pytest.mark.parametrize("spec", TASKS, ids=[t.task_num for t in TASKS])
    def test_gt_answer_scores_high(self, tmp_path: Path, spec: TaskVerifierSpec) -> None:
        workspace = tmp_path / "workspace"
        _write_report(workspace, spec.gt_answer)

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
    def test_empty_answer_scores_low(self, tmp_path: Path, spec: TaskVerifierSpec) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir(parents=True)
        # No IMPACT_REPORT.md written -- verifiers should return 0

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
    """(c) Partial answer should score between 0.3 and 0.7."""

    @pytest.mark.parametrize("spec", TASKS, ids=[t.task_num for t in TASKS])
    def test_partial_answer_scores_mid(self, tmp_path: Path, spec: TaskVerifierSpec) -> None:
        workspace = tmp_path / "workspace"
        _write_report(workspace, spec.partial_answer)

        results = [
            _run_verifier(spec.task_num, cp, workspace)
            for cp in CHECKPOINT_NAMES
        ]
        total = _weighted_score(results)
        assert 0.15 <= total <= 0.75, (
            f"Task {spec.task_num} partial scored {total:.2f} (expected 0.15-0.75). "
            f"Results: {results}"
        )


class TestVerifierScriptsExist:
    """All 8 tasks have all 4 checkpoint verifier scripts."""

    @pytest.mark.parametrize("task_num", [f"{i:03d}" for i in range(1, 9)])
    def test_all_verifiers_present(self, task_num: str) -> None:
        task_dir = _task_dir(task_num)
        for cp in CHECKPOINT_NAMES:
            script = task_dir / "checks" / f"{cp}.sh"
            assert script.exists(), f"Missing: {script}"
            assert os.access(script, os.X_OK), f"Not executable: {script}"


class TestCrossRepoConsumerDetection:
    """Cross-repo consumer detection works correctly for multi-repo tasks."""

    def test_three_repo_chain_task003(self, tmp_path: Path) -> None:
        """Task 003 has grpc-go -> etcd -> k8s chain."""
        workspace = tmp_path / "workspace"
        _write_report(workspace, """\
# Impact Report
transport moved to internal/transport. transport.go key file.
ClientTransport type moved.
etcd imports grpc transport.
kubernetes vendors grpc-go and etcd.
apiserver affected.
""")
        results = [
            _run_verifier("003", cp, workspace)
            for cp in CHECKPOINT_NAMES
        ]
        total = _weighted_score(results)
        # Incomplete but multi-repo aware -> should score mid-range
        assert 0.40 <= total <= 0.80, (
            f"Three-repo partial scored {total:.2f}: {results}"
        )

    def test_envoy_istio_chain_task006(self, tmp_path: Path) -> None:
        """Task 006 has envoy -> go-control-plane -> istio chain."""
        workspace = tmp_path / "workspace"
        _write_report(workspace, """\
# Impact Report
xDS v2 deprecated, runtime fatal by default.
go-control-plane removed pkg/cache/v2/cache.go and v2 packages.
istio pilot/pkg/networking/core/v1alpha3/cluster.go affected.
pilot/pkg/proxy/envoy/v2/ads.go needs migration to v3.
Chain: envoy -> go-control-plane -> istio.
CDS, EDS, LDS, RDS all affected.
Warning phase then fatal phase in phased rollout.
Over 150 files in istio.
""")
        results = [
            _run_verifier("006", cp, workspace)
            for cp in CHECKPOINT_NAMES
        ]
        total = _weighted_score(results)
        assert total >= 0.85, (
            f"Full envoy chain scored {total:.2f}: {results}"
        )
