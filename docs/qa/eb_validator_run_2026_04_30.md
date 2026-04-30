# EB validator run — 2026-04-30 (Layer 3 + ScoreResult)

Bead: `EnterpriseBench-1av` (proxy of `dr-2vydrm.3`)
Branch: `feature/eb-1av-unified-scoreresult`
Vendored lib: `benchmark_qa_core` from codeprobe SHA `047df83` (see
`lib/eb_verify/_vendor/benchmark_qa_core/VENDOR.md`).

## Scope

First end-to-end run of the new validator stack:

* **Layer 1** — JSON Schema (unchanged from main).
* **Layer 2** — Semantic rules (unchanged from main).
* **Layer 3** — `benchmark_qa_core` checks via the new
  `lib/eb_verify/qa_adapter.py`, executed in **strict mode** so that
  `error`-severity findings would fail validation.

Run command:

```
PYTHONPATH=lib python3 -m eb_verify.cli validate --json --qa-strict \
  $(find benchmarks -name task.toml -not -path '*/_archived/*' | sort)
```

## Headline numbers

| metric | count |
| --- | --- |
| tasks scanned | 180 |
| **valid in strict mode** | **179** |
| invalid (Layer 2) | 1 |
| invalid (Layer 3) | 0 |
| warnings emitted | 358 |

The corpus is in good shape — Layer 3 surfaced **zero** new errors. The one
strict-mode failure is from the existing Layer 2 (semantic) rules, not from
the new QA layer.

## Findings by class

### Layer 2 errors (1 task)

| task | finding |
| --- | --- |
| `dependency_management/dep-traversal-007` | `difficulty_stratum 'multi_repo' expects 3–5 repo(s), got 2` |

### Layer 3 warnings — `EB_A0` (oracle file existence skipped)

330 occurrences across 154 tasks. This is **expected behaviour**: the
adapter skips A1/B1/B2 lookups when the cloned repo is not present locally.
At runtime under `/workspace/<repo.path>` the check runs against the live
tree. No action required — these go away when the validator runs inside the
sandbox.

### Layer 3 warnings — `F2` (oracle path appears verbatim in instruction.md)

28 occurrences across **22 distinct tasks**. The lib treats verbatim
appearance of an oracle file path inside the agent-visible prompt as a leak
candidate; the adapter downgrades severity from `error` to `warning` because
some EB task families (refactor, monorepo-boundary) legitimately name the
file under investigation.

The 22 tasks split into two camps:

| camp | tasks | rationale |
| --- | --- | --- |
| **Generic manifest filename (likely false positive)** | 11 | Tokens are common build-manifest names (`go.mod`, `package.json`, `pom.xml`, `setup.cfg`) that the prompt naturally references; the filename is non-discriminative. |
| **Specific path (review)** | 11 | Tokens are concrete repo-relative paths (`metadata/metadata.go`, `balancer/balancer.go`, `bitnami/consul/values.yaml`, `zerver/migrations/0578_*.py`); each one names a single source file. |

Full task list:

```
$(see /tmp/f2_full_list.txt — also reproduced below)
```

#### Specific-path camp (review)

* `dependency_management/api-contract-001` — token `metadata/metadata.go`
* `dependency_management/api-contract-002` — token `balancer/balancer.go`
* `dependency_management/api-contract-005` — token `internal/status/status.go`
* `feature_delivery/monorepo-boundary-001` — token `packages/babel-types/src/definitions/typescript.ts`
* `feature_delivery/monorepo-boundary-006` — token `config/config/src/getOptionsFromRootManifest.ts`
* `feature_delivery/schema-evolution-001` — token `zerver/migrations/0578_namedusergroup_deactivated.py`
* `feature_delivery/schema-evolution-002` — token `zerver/migrations/0595_add_realmexport_table_and_backfill.py`
* `feature_delivery/schema-evolution-004` — token `zerver/migrations/0776_realm_default_avatar_source.py`
* `incident_response/incident-investigation-dual-nats-001` — token `nats.go`
* `platform_engineering/config-drift-001` — token `bitnami/consul/values.yaml`
* `platform_engineering/config-drift-004` — token `manifests/ha/base/redis-ha/chart/values.yaml`
* `security_operations/rbac-audit-001` — token `webhooks/pkg/rbac/rbac.go`

#### Generic-manifest camp (likely false positive)

* `dependency_management/api-contract-007` — token `go.mod`
* `dependency_management/dep-traversal-001` — token `package.json`
* `dependency_management/dep-traversal-002` — token `package.json`
* `dependency_management/dep-traversal-003` — token `go.mod`
* `dependency_management/dep-traversal-004` — token `go.mod`
* `dependency_management/dep-traversal-005` — token `go.mod`
* `dependency_management/dep-traversal-006` — token `go.mod`
* `dependency_management/dep-traversal-008` — token `setup.cfg`
* `dependency_management/dep-traversal-010` — token `pom.xml`
* `technical_debt/refactor-orchestration-006` — token `go.mod`

## Cross-reference with prior beads

* `EnterpriseBench-13t` (closed): Go-balance audit. None of the 11 tasks
  triaged there appear in the F2 list.
* `EnterpriseBench-0rv.25` (closed): 4 ground-truth correctness bugs in the
  2026-04-29 dual-repo task batch. All four (`dead-code-dual-spring-hibernate-001`,
  `schema-evolution-dual-spring-flyway-001`, `config-drift-dual-tokio-hyper-001`,
  `dep-graph-dual-nextjs-webpack-001`) come back **clean** in this run — Layer
  3 surfaces no new findings against them, and the F2 hits there have already
  been triaged.

## Sample ScoreResult emission

The unified ScoreResult contract is now emitted alongside `reward.txt` from
`CheckpointRunner.run_all()`. Sample for `api-contract-grpc-metadata-001`
with hypothetical agent output:

```json
{
  "task_id": "api-contract-grpc-metadata-001",
  "reward": 0.7625,
  "scorer_family": "checklist",
  "sub_scores": {
    "identify_breaking_api": 1.0,
    "find_direct_consumers": 0.85,
    "trace_transitive_impact": 0.4,
    "classify_breakage": 1.0
  },
  "diagnostics": {
    "task_time_seconds": 283.4,
    "token_cost_usd": 0.0145,
    "ir_metrics": null,
    "artifact_results": {
      "answer": {"valid": true, "detail": "answer.json parsed successfully"},
      "incident_report": {"valid": false, "detail": "no markdown report found"}
    }
  }
}
```

`task_time_seconds` and `token_cost_usd` are plumbed in from the harness
layer via `runner.run_all(task_time_seconds=…, token_cost_usd=…)`. These
were previously scattered across `analyze_scores.py` and `reward.txt`;
consolidating them here is the deliverable for sub-task 3b.

## Follow-ups filed

Discovered from `EnterpriseBench-1av`:

* **`EnterpriseBench-3sk`** (bug, P2) — Fix `dep-traversal-007`
  difficulty_stratum/repo-count mismatch. Either drop to `dual_repo` or
  add a third repo.
* **`EnterpriseBench-pyh`** (task, P3) — Triage F2 leakage warnings for
  the 11 tasks that name a specific repo-relative path in
  `instruction.md`. Per-task redact / accept / waive verdicts.
* **`EnterpriseBench-7en`** (task, P3) — Add basename filter to
  `benchmark_qa_core.check_aux_file_leakage` (preferred) or the EB
  adapter, so generic build-manifest filenames (`go.mod`, `package.json`,
  `pom.xml`, `setup.cfg`, `requirements.txt`, `Cargo.toml`, …) don't
  trigger F2 false positives.

## Files modified

* `lib/eb_verify/_vendor/benchmark_qa_core/` (new) — vendored lib copy
  with `VENDOR.md` recording sha256s and drift policy.
* `lib/eb_verify/qa_adapter.py` (new) — EB rig adapter bridging task-meta
  artifacts into `benchmark_qa_core` shapes.
* `lib/eb_verify/scoring.py` — added `ScoreResult`, `ScoreDiagnostics`,
  `write_score_result`, and `VerificationResult.to_score_result`.
* `lib/eb_verify/schema_validator.py` — added Layer 3 (`_run_qa_layer`);
  `validate_task` now accepts `qa_strict` and `workspace_root` kwargs.
* `lib/eb_verify/runner.py` — `run_all` plumbs ScoreResult emission and
  accepts `task_time_seconds` / `token_cost_usd`.
* `lib/eb_verify/cli.py` — `validate` subcommand now accepts
  `--qa-strict` and `--workspace`.
* `lib/eb_verify/__init__.py` — exports new ScoreResult API.
* `tests/test_score_result.py` (new) — 17 tests covering ScoreResult shape.
* `tests/test_qa_adapter.py` (new) — 17 tests covering the QA adapter.

## Test verification

```
$ PYTHONPATH=lib python3 -m pytest \
    tests/test_scoring.py tests/test_schema_validator.py \
    tests/test_score_result.py tests/test_qa_adapter.py \
    tests/test_runner.py tests/test_cli.py
114 passed in 0.27s
```
