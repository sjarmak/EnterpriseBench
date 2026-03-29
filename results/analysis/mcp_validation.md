# MCP Benefit Rationale Validation

**Total tasks audited:** 109
**Tasks with sample runs:** 9
**Tasks with flags:** 8
**Clean tasks:** 101

## Expected MCP Benefit Distribution

| Expected Benefit | Count |
| ---------------- | ----- |
| low              | 14    |
| medium           | 52    |
| high             | 43    |

## Empirical Validation (Tasks with Sample Runs)

| Task                       | Expected | Baseline | MCP  | Gap  | Status               |
| -------------------------- | -------- | -------- | ---- | ---- | -------------------- |
| err-provenance-01          | high     | 0.50     | 1.00 | 0.50 | OK                   |
| err-provenance-06          | high     | 0.59     | 1.00 | 0.41 | OK                   |
| support-mapping-001        | high     | 0.50     | 1.00 | 0.50 | OK                   |
| api-contract-003           | high     | 0.80     | 1.00 | 0.20 | GAP TOO SMALL (0.20) |
| dep-traversal-003          | medium   | 0.82     | 1.00 | 0.18 | OK                   |
| monorepo-boundary-003      | medium   | 0.72     | 1.00 | 0.28 | OK                   |
| schema-evolution-005       | high     | 0.50     | 1.00 | 0.50 | OK                   |
| dead-code-001              | high     | 0.41     | 0.96 | 0.55 | OK                   |
| refactor-orchestration-003 | high     | 0.62     | 1.00 | 0.38 | OK                   |

## Plausibility Assessment (All Tasks)

| Task                                    | Expected | Repos | Stratum                | Rationale (truncated)                                            | Plausible? |
| --------------------------------------- | -------- | ----- | ---------------------- | ---------------------------------------------------------------- | ---------- |
| calibration-001                         | low      | 1     | calibration            | Flask is a small codebase; the Blueprint registration logic ...  | yes        |
| calibration-002                         | low      | 1     | calibration            | Click is a small library; flag_value handling is in a single...  | yes        |
| calibration-003                         | low      | 1     | calibration            | Requests is a small library; proxy header handling can be fo...  | yes        |
| calibration-004                         | low      | 1     | calibration            | Flask is a small codebase; the request lifecycle is linear a...  | yes        |
| calibration-005                         | low      | 1     | calibration            | Click is small; grep for Sentinel immediately finds the rele...  | yes        |
| calibration-006                         | low      | 1     | calibration            | Flask is small; errorhandler is easily found by grep in scaf...  | yes        |
| calibration-007                         | low      | 1     | calibration            | Requests is small; REQUESTS_CA_BUNDLE handling is in utils.p...  | yes        |
| calibration-008                         | low      | 1     | calibration            | Click testing module is self-contained; CliRunner is in a si...  | yes        |
| err-provenance-01                       | high     | 1     | large_single           | Navigating the Job API validation chain across Kubernetes st...  | REVIEW     |
| err-provenance-010                      | medium   | 1     | large_single           | Panic points to the file but not the condition; MCP helps na...  | yes        |
| err-provenance-02                       | medium   | 1     | large_single           | Error wraps through kube-proxy into the vendored knftables l...  | yes        |
| err-provenance-03                       | medium   | 1     | large_single           | Multiple interleaved error messages from different subsystem...  | yes        |
| err-provenance-04                       | medium   | 1     | large_single           | No visible error string to grep directly, but prober worker ...  | yes        |
| err-provenance-05                       | medium   | 1     | large_single           | The warning string is easy to locate, but understanding why ...  | yes        |
| err-provenance-06                       | high     | 1     | large_single           | User-visible error (gRPC invalid UTF-8) is completely differ...  | REVIEW     |
| err-provenance-07                       | medium   | 1     | large_single           | The error string is easy to locate, but tracing it to the bu...  | yes        |
| err-provenance-08                       | medium   | 1     | large_single           | Panic hides the real error (permission denied); MCP helps tr...  | yes        |
| err-provenance-09                       | low      | 1     | large_single           | Direct string match in error constants file; minimal MCP ben...  | yes        |
| support-mapping-001                     | high     | 1     | large_single           | Large C++ codebase with deep call chains; MCP search acceler...  | REVIEW     |
| support-mapping-002                     | high     | 1     | large_single           | Massive monorepo; tracing assertion string through type lega...  | REVIEW     |
| support-mapping-003                     | medium   | 1     | large_single           | Full-stack Go+TypeScript codebase; import flow spans backend...  | yes        |
| support-mapping-004                     | medium   | 1     | large_single           | Alert scheduler is well-contained in ngalert package; MCP he...  | yes        |
| support-mapping-005                     | high     | 1     | large_single           | Massive Go monorepo; eviction logic spans kubelet, node stat...  | REVIEW     |
| support-mapping-006                     | high     | 1     | large_single           | Enormous mixed C++/Rust codebase; CSS processing spans Gecko...  | REVIEW     |
| support-mapping-007                     | high     | 1     | large_single           | Enormous C++ monorepo; formula engine spans compiler, interp...  | REVIEW     |
| support-mapping-008                     | medium   | 1     | large_single           | Medium-sized Python codebase; ad-blocker cache path is somew...  | yes        |
| support-mapping-009                     | medium   | 1     | large_single           | Medium TypeScript codebase; component hierarchy is discovera...  | yes        |
| support-mapping-010                     | medium   | 1     | large_single           | Notification state spans multiple stores and utilities; MCP ...  | yes        |
| support-mapping-011                     | medium   | 1     | large_single           | Medium JavaScript codebase; two separate bugs (notifications...  | yes        |
| support-mapping-012                     | medium   | 1     | large_single           | Race condition spans multiple producer internals with subtle...  | yes        |
| api-contract-001                        | high     | 2     | dual_repo              | Cross-repo symbol search for metadata.FromContext usage acro...  | yes        |
| api-contract-002                        | high     | 2     | dual_repo              | Cross-repo interface implementation search needed to find al...  | yes        |
| api-contract-003                        | high     | 3     | multi_repo             | Three-repo dependency chain (grpc-go → etcd → kubernetes) re...  | yes        |
| api-contract-004                        | high     | 2     | dual_repo              | Interface implementation search across repos requires semant...  | yes        |
| api-contract-005                        | medium   | 1     | large_single           | Single-repo analysis but requires understanding protobuf typ...  | yes        |
| api-contract-006                        | high     | 3     | multi_repo             | Three-repo proto definition chain requires tracing xDS type ...  | yes        |
| api-contract-007                        | medium   | 3     | multi_repo             | Module-level analysis requires understanding Go module resol...  | yes        |
| api-contract-008                        | medium   | 1     | large_single           | Cross-repo interface implementation search to find all cel.P...  | yes        |
| ccx-dep-trace-106                       | medium   | 1     | large_single           | GCC pass infrastructure uses macro-based registration in pas...  | yes        |
| dep-traversal-001                       | high     | 3     | multi_repo             | Cross-repo dependency graph traversal through npm package ma...  | yes        |
| dep-traversal-002                       | high     | 3     | multi_repo             | Cross-repo npm dependency resolution through lock files and ...  | yes        |
| dep-traversal-003                       | medium   | 2     | dual_repo              | Go module graph is parseable from go.mod, but function-level...  | yes        |
| dep-traversal-004                       | high     | 3     | multi_repo             | Go module graph traversal across CNCF repos requires cross-r...  | yes        |
| dep-traversal-005                       | high     | 3     | multi_repo             | Three large Go codebases with deep module graphs — Sourcegra...  | yes        |
| dep-traversal-006                       | high     | 3     | multi_repo             | Protobuf Any type usage requires cross-repo symbol search th...  | yes        |
| dep-traversal-007                       | high     | 2     | multi_repo             | Cross-repo npm dependency chain traversal through nested pac...  | yes        |
| dep-traversal-008                       | high     | 3     | multi_repo             | Python dependency chain through setup.py/setup.cfg/requireme...  | yes        |
| dep-traversal-009                       | high     | 3     | multi_repo             | 3-hop Python dependency chain with vendoring complexity bene...  | yes        |
| dep-traversal-010                       | high     | 3     | tri_repo               | Maven BOM inheritance chain traversal requires understanding...  | yes        |
| dep-traversal-011                       | high     | 3     | multi_repo             | Shaded/relocated JAR detection and Maven BOM traversal throu...  | yes        |
| dep-traversal-012                       | medium   | 3     | multi_repo             | Cross-ecosystem system library tracing partially benefits fr...  | yes        |
| aspnetcore-code-review-001              | medium   | 1     | large_single           | Single-repo code review; MCP helps navigate ASP.NET Core com...  | yes        |
| camel-routing-arch-001                  | medium   | 1     | large_single           | Single-repo but very large codebase (~2.8M LOC); MCP symbol ...  | yes        |
| monorepo-boundary-001                   | high     | 1     | monorepo_cross_package | Cross-package type reference tracing through barrel re-expor...  | yes        |
| monorepo-boundary-002                   | high     | 1     | monorepo_cross_package | Tracing decorator helper consumption through re-exports and ...  | yes        |
| monorepo-boundary-003                   | medium   | 1     | monorepo_cross_package | Two independent changes converging requires tracing decorato...  | yes        |
| monorepo-boundary-004                   | medium   | 1     | monorepo_cross_package | Bug fixes are localized but the for-of fix affects preset-en...  | yes        |
| monorepo-boundary-005                   | high     | 1     | monorepo_cross_package | workspace:\* protocol dependencies create a complex internal ... | yes        |
| monorepo-boundary-006                   | high     | 1     | monorepo_cross_package | Config value consumption is spread across packages via funct...  | yes        |
| monorepo-boundary-007                   | high     | 1     | monorepo_cross_package | Hash function consumers are spread across content-addressabl...  | yes        |
| monorepo-boundary-008                   | high     | 1     | monorepo_cross_package | Cross-language boundary (TypeScript → Rust) requires finding...  | yes        |
| monorepo-boundary-009                   | high     | 1     | monorepo_cross_package | Cargo workspace dependency graph + use path tracing across 5...  | yes        |
| monorepo-boundary-010                   | high     | 1     | monorepo_cross_package | MIR representation changes cascade through the compiler pipe...  | yes        |
| schema-evolution-001                    | medium   | 1     | large_single           | Tracing a new boolean field through Django model → actions →...  | yes        |
| schema-evolution-002                    | medium   | 1     | large_single           | Creating a new RealmExport model requires tracing all export...  | yes        |
| schema-evolution-003                    | medium   | 1     | large_single           | Replacing a boolean policy with a FK to NamedUserGroup requi...  | yes        |
| schema-evolution-004                    | medium   | 1     | large_single           | Moving default_avatar_source between UserProfile and Realm r...  | yes        |
| schema-evolution-005                    | high     | 1     | large_single           | Rails MVC tracing through model hierarchy, 3 serializers, gu...  | REVIEW     |
| schema-evolution-006                    | medium   | 1     | large_single           | Standard Rails MVC tracing with frontend component reference...  | yes        |
| schema-evolution-007                    | medium   | 1     | large_single           | Two-phase migration pattern with boolean-to-join-table norma...  | yes        |
| schema-evolution-008                    | medium   | 1     | large_single           | Two-step migration with API response schema fixtures is a co...  | yes        |
| schema-evolution-009                    | medium   | 1     | large_single           | Creating DashboardLastVisited requires cross-layer tracing f...  | yes        |
| schema-evolution-010                    | medium   | 1     | large_single           | Dropping the icon column and removing nested subviews touche...  | yes        |
| ansible-abc-imports-fix-001             | medium   | 1     | large_single           | Single-repo Python codebase; the import pattern is easy to f...  | yes        |
| ansible-galaxy-tar-regression-prove-001 | medium   | 1     | large_single           | Single-repo; root cause is in Galaxy collection module — MCP...  | yes        |
| ccx-incident-032                        | medium   | 1     | large_single           | Tracing connection pool overflow requires following reset re...  | yes        |
| incident-investigation-001              | medium   | 1     | large_single           | Watch request flow crosses staging package boundaries from t...  | yes        |
| incident-investigation-002              | medium   | 1     | large_single           | Tracing resourceVersion propagation across the watch cache a...  | yes        |
| incident-investigation-003              | high     | 2     | dual_repo              | Cross-repo investigation: understanding how Prometheus API r...  | yes        |
| incident-investigation-004              | medium   | 1     | large_single           | Tracing spurious restart warnings requires following the shu...  | yes        |
| calibration-001                         | low      | 1     | calibration            | Flask config system is in a single file; simple grep finds a...  | yes        |
| calibration-002                         | low      | 1     | calibration            | Click parameter resolution is in core.py; the precedence log...  | yes        |
| config-drift-001                        | medium   | 1     | large_single           | Cross-file search helps trace port value references from val...  | yes        |
| config-drift-002                        | medium   | 1     | large_single           | Tracing external RabbitMQ config flow through a 4-layer Helm...  | yes        |
| config-drift-003                        | medium   | 1     | large_single           | Finding all call sites of the Redis password helper across t...  | yes        |
| config-drift-004                        | medium   | 1     | large_single           | Cross-file search helps trace value override chain from Argo...  | yes        |
| ccx-compliance-052                      | medium   | 1     | large_single           | Access logger implementations are spread across the extensio...  | yes        |
| ccx-compliance-053                      | medium   | 1     | large_single           | Audit logging spans Scala core and Java clients packages; MC...  | yes        |
| ceph-rgw-auth-secure-001                | medium   | 1     | large_single           | Single-repo but large C++ codebase; MCP helps navigate the R...  | yes        |
| rbac-audit-001                          | medium   | 1     | large_single           | Single large repo but requires cross-component analysis betw...  | yes        |
| rbac-audit-002                          | medium   | 1     | large_single           | Large single repo requiring navigation of permission model a...  | yes        |
| rbac-audit-003                          | medium   | 1     | large_single           | Single repo requiring cross-package analysis between securit...  | yes        |
| rbac-audit-004                          | low      | 1     | large_single           | Single file analysis — standard code search is sufficient        | yes        |
| beam-pipeline-builder-refac-001         | medium   | 1     | large_single           | Single-repo Java refactoring; MCP helps navigate the Pipelin...  | yes        |
| calibration-001                         | low      | 1     | calibration            | Click is small enough that grep -r can exhaustively check al...  | yes        |
| calibration-002                         | low      | 1     | calibration            | Flask is a small codebase; exhaustive grep can verify all re...  | yes        |
| dead-code-001                           | high     | 1     | large_single           | Dead code detection requires exhaustive reference search to ...  | REVIEW     |
| dead-code-002                           | high     | 1     | large_single           | Proving feature flag branches are dead requires exhaustive s...  | REVIEW     |
| dead-code-003                           | medium   | 1     | large_single           | Compiler pipeline is contained within a single package direc...  | yes        |
| dead-code-004                           | high     | 1     | large_single           | Proving exports are dead in a 900K LoC TypeScript compiler r...  | REVIEW     |
| dead-code-005                           | high     | 1     | large_single           | Proving ViewEngine code is dead requires exhaustive search a...  | REVIEW     |
| refactor-orchestration-001              | high     | 2     | dual_repo              | Cross-repo dependency graph traversal through go.mod files b...  | yes        |
| refactor-orchestration-002              | medium   | 2     | dual_repo              | Dependency graph traversal through go.mod to find all cobra ...  | yes        |
| refactor-orchestration-003              | high     | 3     | tri_repo               | 3-repo dependency chain requires cross-repo go.mod analysis ...  | yes        |
| refactor-orchestration-004              | high     | 3     | tri_repo               | Import path migration requires finding all protobuf imports ...  | yes        |
| refactor-orchestration-005              | high     | 1     | monorepo_cross_package | Monorepo internal dependency graph requires resolving packag...  | yes        |
| refactor-orchestration-006              | high     | 1     | monorepo_cross_package | Kubernetes staging repo dependency graph is complex; require...  | yes        |
| refactor-orchestration-007              | high     | 3     | tri_repo               | Finding all grpc.Dial call sites across 3 repos and understa...  | yes        |
| refactor-orchestration-008              | high     | 3     | tri_repo               | Understanding which middleware features are used where acros...  | yes        |

## Flagged Tasks

### support-mapping-002

- **Expected MCP benefit:** high
- **Repos:** 1 | **Stratum:** large_single
- **Rationale:** Massive monorepo; tracing assertion string through type legalization pipeline requires deep code search across SelectionDAG subsystem
- **Flags:**
  - claims high MCP benefit but single-repo (large_single) — grep may suffice unless codebase is very large

### support-mapping-005

- **Expected MCP benefit:** high
- **Repos:** 1 | **Stratum:** large_single
- **Rationale:** Massive Go monorepo; eviction logic spans kubelet, node status reporting, and config types across staging packages
- **Flags:**
  - claims high MCP benefit but single-repo (large_single) — grep may suffice unless codebase is very large

### support-mapping-006

- **Expected MCP benefit:** high
- **Repos:** 1 | **Stratum:** large_single
- **Rationale:** Enormous mixed C++/Rust codebase; CSS processing spans Gecko layout and Servo style engine with complex FFI boundary
- **Flags:**
  - claims high MCP benefit but single-repo (large_single) — grep may suffice unless codebase is very large

### support-mapping-007

- **Expected MCP benefit:** high
- **Repos:** 1 | **Stratum:** large_single
- **Rationale:** Enormous C++ monorepo; formula engine spans compiler, interpreter (split across many files), and cell dependency tracking
- **Flags:**
  - claims high MCP benefit but single-repo (large_single) — grep may suffice unless codebase is very large

### api-contract-003

- **Expected MCP benefit:** high
- **Repos:** 3 | **Stratum:** multi_repo
- **Baseline:** 0.80 | **MCP:** 1.00 | **Gap:** 0.20
- **Rationale:** Three-repo dependency chain (grpc-go → etcd → kubernetes) requires cross-repo import graph traversal. Transport types are re-exported and wrapped across package boundaries, so direct consumers are findable with text search but transitive impact through re-exports requires semantic navigation
- **Flags:**
  - expected high but actual gap=0.20 (<0.3): baseline=0.80, mcp=1.00

### dead-code-002

- **Expected MCP benefit:** high
- **Repos:** 1 | **Stratum:** large_single
- **Rationale:** Proving feature flag branches are dead requires exhaustive search for all enableRenderableContext references across React packages and fork files; MCP accelerates confirming zero live callers of dead branches
- **Flags:**
  - claims high MCP benefit but single-repo (large_single) — grep may suffice unless codebase is very large

### dead-code-004

- **Expected MCP benefit:** high
- **Repos:** 1 | **Stratum:** large_single
- **Rationale:** Proving exports are dead in a 900K LoC TypeScript compiler requires exhaustive cross-file reference search; MCP accelerates confirming zero importers across compiler, services, and server layers
- **Flags:**
  - claims high MCP benefit but single-repo (large_single) — grep may suffice unless codebase is very large

### dead-code-005

- **Expected MCP benefit:** high
- **Repos:** 1 | **Stratum:** large_single
- **Rationale:** Proving ViewEngine code is dead requires exhaustive search across Angular's package structure to confirm no remaining imports; MCP accelerates confirming zero callers of ViewEngine-specific modules vs Ivy replacements
- **Flags:**
  - claims high MCP benefit but single-repo (large_single) — grep may suffice unless codebase is very large

## Summary

- **empirical score mismatch:** 1 tasks
- **high benefit + single repo:** 7 tasks
