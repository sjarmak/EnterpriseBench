"""Verification tests for dep-traversal task checkpoint scripts.

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

# -- task definitions ---------------------------------------------------------


@dataclass(frozen=True)
class TaskVerifierSpec:
    """Spec for testing one task's verifiers."""

    task_num: str
    # Ground truth answer content -- what a perfect agent would write
    gt_answer: str
    # Partial answer -- some but not all info found
    partial_answer: str


TASKS: list[TaskVerifierSpec] = [
    TaskVerifierSpec(
        task_num="001",
        gt_answer="""\
# Blast Radius Report

## CVE Identification
CVE-2021-23337 affects `lodash` versions < 4.17.21. Command injection via
`_.template` function.

## Direct Dependents
- **webpack** — `package.json` lists lodash as devDependency
- **jest** — `packages/jest-haste-map/package.json` depends on lodash
- **@babel/traverse** — internal usage of lodash utilities

## Transitive Paths
- lodash -> webpack -> create-react-app
- lodash -> jest-haste-map -> jest -> create-react-app
- lodash -> babel-loader -> webpack (circular via @babel/traverse)

## Version Analysis
- webpack v5.64.0: lodash pinned at 4.17.20 — **affected**, needs upgrade
- jest v29.0.0: lodash resolved to 4.17.21 — **not affected**, already patched
""",
        partial_answer="""\
# Blast Radius Report

## CVE-2021-23337
Affects lodash < 4.17.21.

## Direct Dependents
- webpack uses lodash
""",
    ),
    TaskVerifierSpec(
        task_num="002",
        gt_answer="""\
# Blast Radius Report

## CVE Identification
CVE-2021-3749 affects `axios` versions < 0.21.2. ReDoS via trim function.

## Direct Dependents
- **grafana** — package.json, used in plugin SDK and frontend
- **druid** — web-console/package.json, HTTP client for Druid web console

## Transitive Paths
- axios -> grafana plugin SDK -> grafana plugins
- axios -> druid web-console -> druid frontend

## Version Analysis
- grafana v9.5.0: axios pinned at 0.21.1 — **affected**, needs upgrade to 0.21.2+
- druid web-console: axios 0.21.1 — **still vulnerable**, needs upgrade
""",
        partial_answer="""\
# Blast Radius Report

## CVE-2021-3749
Affects axios < 0.21.2.

## Dependents
- grafana uses axios
""",
    ),
    TaskVerifierSpec(
        task_num="003",
        gt_answer="""\
# Blast Radius Report

## CVE Identification
CVE-2022-32149 affects `golang.org/x/text` versions < 0.3.8. DoS via
ParseAcceptLanguage function.

## Direct Dependents (go.mod)
- **chi** (go-chi/chi) — go.mod lists golang.org/x/text
- **hugo** (gohugoio/hugo) — go.mod lists golang.org/x/text

## Function-Level Analysis: ParseAcceptLanguage
- chi: Does NOT directly call ParseAcceptLanguage — only imports x/text/transform
  for middleware. Not affected by this specific vulnerability.
- hugo: Uses the language package for i18n. May call Accept-Language parsing.

## Version Analysis
- chi v5.0.8: x/text resolved to 0.3.7 in go.mod — **affected** version but
  not calling vulnerable function
- hugo v0.111.0: x/text at 0.5.0 — **not affected**, already patched
""",
        partial_answer="""\
# Blast Radius Report

## CVE-2022-32149
Affects golang.org/x/text < 0.3.8.

## Dependents
- chi depends on x/text (go.mod)
""",
    ),
    TaskVerifierSpec(
        task_num="004",
        gt_answer="""\
# Blast Radius Report

## CVE Identification
CVE-2023-39325 affects `golang.org/x/net` versions < 0.17.0. HTTP/2 Rapid Reset
denial of service.

## Direct Dependents
- **kubernetes** — go.mod lists golang.org/x/net (API server, kubelet)
- **etcd** — go.mod lists golang.org/x/net
- **grpc-go** — go.mod lists golang.org/x/net for http2 transport

## Transitive Paths
- golang.org/x/net -> grpc-go (http2 transport layer) -> etcd (gRPC client/server)
- golang.org/x/net -> kubernetes (API server direct dependency)
- golang.org/x/net -> grpc-go -> kubernetes (gRPC services)

## Version Analysis
- kubernetes v1.28.0: x/net resolved in go.sum to 0.12.0 — **affected**
- etcd v3.5.9: x/net at 0.10.0 — **affected**, needs upgrade
- grpc-go v1.58.0: x/net at 0.14.0 — **affected**, needs upgrade to 0.17.0+
""",
        partial_answer="""\
# Blast Radius Report

## CVE-2023-39325
Affects golang.org/x/net < 0.17.0.

## Dependents
- kubernetes depends on x/net (go.mod)
- etcd depends on x/net
""",
    ),
    TaskVerifierSpec(
        task_num="005",
        gt_answer="""\
# Blast Radius Report

## CVE Identification
CVE-2022-41723 affects `golang.org/x/net` versions < 0.7.0. HPACK header
compression DoS in HTTP/2 server.

## Direct Dependents
- **prometheus** — go.mod lists golang.org/x/net
- **consul** — go.mod lists golang.org/x/net
- **vault** — go.mod lists golang.org/x/net

## Transitive Paths
- golang.org/x/net -> prometheus/prometheus (HTTP/2 server for metrics endpoints)
- golang.org/x/net -> consul (gRPC and HTTP/2 for service discovery)
- golang.org/x/net -> vault (HTTPS listeners)

## Version Analysis
- prometheus v2.45.0: x/net resolved in go.sum to 0.9.0 — **not affected**, already patched
- consul v1.16.0: x/net at 0.8.0 — **not affected**, already patched
- vault v1.14.0: x/net at 0.7.0 — **patched** at exact fix version
""",
        partial_answer="""\
# Blast Radius Report

## CVE-2022-41723
Affects golang.org/x/net < 0.7.0.

## Dependents
- prometheus has x/net in go.mod
""",
    ),
    TaskVerifierSpec(
        task_num="006",
        gt_answer="""\
# Blast Radius Report

## CVE Identification
CVE-2024-24786 affects `google.golang.org/protobuf` versions < 1.33.0. Infinite
loop when unmarshaling JSON containing Any protobuf types.

## Direct Dependents
- **grpc-go** — go.mod lists google.golang.org/protobuf
- **istio** — go.mod lists google.golang.org/protobuf
- **go-control-plane** — go.mod lists google.golang.org/protobuf

## Transitive Paths
- google.golang.org/protobuf -> grpc-go (protobuf message marshaling) -> istio
- google.golang.org/protobuf -> go-control-plane (xDS config) -> istio
- Istio uses protojson.Unmarshal with Any types for xDS configuration

## Version Analysis
- grpc-go v1.62.0: protobuf at 1.32.0 — **affected**, needs upgrade to 1.33.0+
- istio 1.20.0: protobuf at 1.31.0 — **affected**
- go-control-plane v0.12.0: protobuf at 1.31.0 — **affected**
""",
        partial_answer="""\
# Blast Radius Report

## CVE-2024-24786
Affects google.golang.org/protobuf < 1.33.0.

## Dependents
- grpc-go uses protobuf
""",
    ),
    TaskVerifierSpec(
        task_num="007",
        gt_answer="""\
# Blast Radius Report

## CVE Identification
CVE-2022-25878 affects `protobufjs` (npm) — prototype pollution. Affected
versions: 6.10.0-6.10.2 and 6.11.0-6.11.2. Fixed in 6.10.3 / 6.11.3.

## Direct Dependents
- **grpc-node** — packages/grpc-js/package.json depends on protobufjs
- **kubernetes-client-js** — package.json depends on @grpc/grpc-js transitively

## Transitive Paths
- protobufjs -> @grpc/grpc-js -> kubernetes-client/javascript
- protobufjs -> @grpc/grpc-js (used for gRPC transport)

## Version Analysis
- grpc-node grpc-js: protobufjs at 6.11.2 in lock file — **affected**
- kubernetes-client: depends on grpc-js which pulls in affected protobufjs — **affected** transitively
""",
        partial_answer="""\
# Blast Radius Report

## CVE-2022-25878
Affects protobufjs 6.10.0-6.10.2.

## Dependents
- grpc-node uses protobufjs
""",
    ),
    TaskVerifierSpec(
        task_num="008",
        gt_answer="""\
# Blast Radius Report

## CVE Identification
CVE-2023-32681 affects `requests` (PyPI) versions >= 2.3.0, < 2.31.0.
Proxy-Authorization header leak on redirect.

## Direct Dependents
- **botocore** — setup.py lists requests as dependency
- **boto3** — depends on botocore which depends on requests
- **awscli** (aws-cli) — setup.py lists botocore and boto3

## Transitive Paths
- requests -> botocore -> boto3 -> awscli (3-hop chain)
- requests -> botocore -> awscli (direct)

## Version Analysis
- boto3 1.26.0: botocore pins requests>=2.25.0,<2.29 in setup.py — **affected**
- awscli 2.11.0: inherits requests version from botocore — **affected**, needs upgrade to requests 2.31.0+
""",
        partial_answer="""\
# Blast Radius Report

## CVE-2023-32681
Affects requests < 2.31.0. Proxy-Authorization header leak.

## Dependents
- boto3 depends on requests via botocore
""",
    ),
    TaskVerifierSpec(
        task_num="009",
        gt_answer="""\
# Blast Radius Report

## CVE Identification
CVE-2023-43804 affects `urllib3` (PyPI). Two branches affected:
- 1.x: < 1.26.17
- 2.x: 2.0.0-2.0.5

Cookie header leak on cross-origin redirect.

## Direct Dependents
- **requests** — setup.cfg lists urllib3 as transport layer dependency

## Transitive Paths
- urllib3 -> requests -> botocore -> boto3 (3-hop transitive chain)
- requests vendors/pins urllib3 1.x branch

## Version Analysis
- requests v2.28.0: pins urllib3>=1.21.1,<1.27 — uses 1.x branch, version
  1.26.16 — **affected**, needs 1.26.17+
- boto3 1.26.0: inherits urllib3 version through botocore -> requests chain — **affected** transitively
""",
        partial_answer="""\
# Blast Radius Report

## CVE-2023-43804
Affects urllib3 < 1.26.17.

## Dependents
- requests uses urllib3 as transport layer
""",
    ),
    TaskVerifierSpec(
        task_num="010",
        gt_answer="""\
# Blast Radius Report

## CVE Identification
CVE-2020-36518 affects `com.fasterxml.jackson.core:jackson-databind` versions
<= 2.12.6.0 (fix 2.12.6.1) and 2.13.0-2.13.2 (fix 2.13.2.1). Deep nesting DoS.

## Direct Dependents
- **spring-boot** — spring-boot-dependencies manages jackson-databind version
  via BOM (Bill of Materials)
- **dropwizard** — dropwizard-jackson module depends on jackson-databind

## Transitive Paths
- jackson-databind -> jackson-bom -> spring-boot-dependencies -> spring-boot-starter-web
- jackson-databind -> dropwizard-jackson -> dropwizard-core
- BOM dependency management means version is inherited, not declared directly in pom.xml

## Version Analysis
- spring-boot v2.7.0: manages jackson-databind 2.13.3 via build.gradle — **not affected** (post-fix)
- dropwizard v2.1.0: jackson-databind 2.13.2 in dropwizard-bom/pom.xml — **affected**, needs 2.13.2.1+
""",
        partial_answer="""\
# Blast Radius Report

## CVE-2020-36518
Affects jackson-databind <= 2.12.6.0 and 2.13.0-2.13.2.

## Dependents
- spring-boot uses jackson-databind via BOM
""",
    ),
    TaskVerifierSpec(
        task_num="011",
        gt_answer="""\
# Blast Radius Report

## CVE Identification
CVE-2021-44228 (Log4Shell) affects `org.apache.logging.log4j:log4j-core` versions
2.0-beta9 through 2.14.1. Critical RCE via JNDI lookup injection.
Also affects: pax-logging-log4j2 (shaded/relocated OSGi bundle).

Fix versions: 2.15.0 (partial — still exploitable), 2.16.0 (full fix).
Backports: 2.3.1 (Java 6), 2.12.2 (Java 7).

## Direct Dependents
- **spring-boot** — via spring-boot-starter-log4j2 (optional logging framework)
- **kafka** — build.gradle lists log4j-core as logging dependency

## Transitive Paths
- log4j-core -> spring-boot-starter-log4j2 -> Spring Boot applications
- log4j-core -> kafka-clients -> kafka-streams -> Kafka applications
- JNDI lookup enables remote code execution when attacker-controlled strings are logged

## Version Analysis
- spring-boot v2.6.1: starter-log4j2 manages log4j 2.14.1 — **affected**, 2.15.0 is partial fix only, needs 2.16.0+
- kafka 3.1.0: log4j 2.17.1 in build.gradle — **patched** (post 2.16.0)
""",
        partial_answer="""\
# Blast Radius Report

## CVE-2021-44228
Log4Shell. Affects log4j-core 2.0-beta9 through 2.14.1. JNDI RCE.

## Dependents
- kafka uses log4j-core
""",
    ),
    TaskVerifierSpec(
        task_num="012",
        gt_answer="""\
# Blast Radius Report

## CVE Identification
CVE-2022-0778 affects OpenSSL versions:
- 1.0.2 through 1.0.2zc
- 1.1.1 through 1.1.1m
- 3.0.0 through 3.0.1
BN_mod_sqrt infinite loop triggered by crafted certificates.

## Cross-Ecosystem Consumers
- **curl** — dynamically links OpenSSL for TLS (configure.ac)
- **git** — uses curl for HTTP transport, so inherits curl's OpenSSL dependency
- **Python ssl** module — links against system OpenSSL
- **kubernetes** — Go uses crypto/tls, pure Go by default (CGO_ENABLED=0)

## Transitive Paths
- OpenSSL -> curl -> git -> CI/CD pipelines (dynamic linking)
- OpenSSL -> Python ssl module -> pip -> requests -> boto3 (dynamic linking)
- OpenSSL -> Node.js crypto -> npm ecosystem (static linking in Node.js builds)

## Linking Strategy & Exposure
- curl: **dynamic linking** — affected if system OpenSSL is vulnerable
- git: transitive via curl — **affected** same as curl
- kubernetes: pure Go crypto/tls (CGO_ENABLED=0 default) — **not affected/immune**
  unless built with CGO_ENABLED=1
""",
        partial_answer="""\
# Blast Radius Report

## CVE-2022-0778
Affects OpenSSL 1.1.1 through 1.1.1m. Infinite loop.

## Dependents
- curl uses OpenSSL (dynamic linking)
""",
    ),
]


# -- helpers ------------------------------------------------------------------


def _task_dir(task_num: str) -> Path:
    return BENCHMARKS_DIR / f"dep-traversal-{task_num}"


CHECKPOINT_NAMES = [
    "check_cve_id",
    "check_direct_deps",
    "check_transitive_paths",
    "check_version_analysis",
]

CHECKPOINT_WEIGHTS = (0.10, 0.30, 0.35, 0.25)


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
    env["TASK_ID"] = f"dep-traversal-{task_num}"

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
    """Write a BLAST_RADIUS.md into the workspace root."""
    workspace.mkdir(parents=True, exist_ok=True)
    report_path = workspace / "BLAST_RADIUS.md"
    report_path.write_text(content)
    return report_path


def _weighted_score(
    results: list[dict[str, Any]],
    weights: tuple[float, ...] = CHECKPOINT_WEIGHTS,
) -> float:
    """Compute weighted score from 4 checkpoint results."""
    total = 0.0
    for r, w in zip(results, weights):
        total += float(r.get("score", 0.0)) * w
    return total


# -- tests --------------------------------------------------------------------


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
        # No BLAST_RADIUS.md written -- verifiers should return 0

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
    """All 12 tasks have all 4 checkpoint verifier scripts."""

    @pytest.mark.parametrize("task_num", [f"{i:03d}" for i in range(1, 13)])
    def test_all_verifiers_present(self, task_num: str) -> None:
        task_dir = _task_dir(task_num)
        for cp in CHECKPOINT_NAMES:
            script = task_dir / "checks" / f"{cp}.sh"
            assert script.exists(), f"Missing: {script}"
            assert os.access(script, os.X_OK), f"Not executable: {script}"
