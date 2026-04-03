# Scaffold: EnterpriseBench Publish Pipeline

## Strategy Comparison

| Dimension             | Riskiest-First                          | Demo-able First                         | Dependency-Topological             | Vertical Slice               |
| --------------------- | --------------------------------------- | --------------------------------------- | ---------------------------------- | ---------------------------- |
| First thing built     | Session-chain + event-replay validation | Session-chain + event-replay validation | eb_verify + ground truth hardening | Single-task three-mode proof |
| Time to first demo    | ~3 days                                 | ~3 days                                 | ~7 days                            | ~4 days                      |
| Risk front-loading    | High                                    | Medium                                  | Low                                | High                         |
| Parallelism potential | Low early                               | Strong (3 parallel mid-plan)            | Low (strict sequential)            | Moderate                     |
| Stub/mock debt        | Minimal                                 | Minimal                                 | Zero                               | Moderate early               |
| Integration risk      | Deferred to sweep                       | Managed via integration tests           | Very low                           | Lowest (proven in phase 1)   |

## Convergence Points

- **Session-type validation early** — 3/4 strategies put this in phase 1
- **eb_verify hardening before full sweep** — 4/4 unanimous
- **Ground truth hardening before final data generation** — 4/4 unanimous
- **MCP mirrors before tool-access comparison** — 4/4 hard dependency
- **Paper is terminal** — 4/4 unanimous
- **Two-batch task expansion** — 2/4 prefer this for course-correction

## Recommended Build Plan

### Phase 1: Session-type validation

- Run 2-3 chain tasks + 2 event-replay tasks with real agent
- Fix bugs in chain_runner git-branch handoff and event_replay scoring
- **Done when**: Scored results for chain and event-replay tasks, non-zero scores, correct git state
- **Informed by**: Riskiest-First, Demo-able, Vertical Slice

### Phase 2: Three-mode vertical slice

- Pick one well-scoring calibration task
- Create 1 SG mirror, add mode flag to dispatcher
- Run in baseline/mcp_only/hybrid modes
- Capture tool-usage metadata, store results per-mode
- Produce comparison table (score + tools per mode)
- **Done when**: 3 mode-tagged results for same task, comparison output, tool-usage captured
- **Informed by**: Vertical Slice

### Phase 3: eb_verify hardening

- Oracle matching in answer validator
- git-apply-check in code_patch plugin
- HCL support in config_validator
- Semantic checks in incident_report validator
- Regression tests for all changes
- **Done when**: All 9 plugins pass expanded test suite, 12 calibration tasks re-score within 0.1 of baseline
- **Informed by**: Dependency-Topological, all strategies

### Phase 4: Task expansion (first half ~45 tasks)

- Run ~45 tasks across all suites, prioritizing diversity
- Fix broken task definitions
- Expand MCP mirrors, run in 3 modes where mirrors exist
- **Done when**: ~57 total scored tasks, score distribution has meaningful spread
- **Informed by**: Demo-able, Vertical Slice

### Phase 5: Ground truth hardening

- Deterministic AST/import parsing layer
- Solve-verification loop on scored tasks
- Curator cross-validation
- **Done when**: Deterministic layer covers Python/Go, solve-verification passes on 80%+ tasks
- **Informed by**: Dependency-Topological, Vertical Slice

### Phase 6: Complete sweep + reproducibility

- Run remaining ~45 tasks in 3 modes
- Reproducibility: 3x runs on 20-30 task subset, variance < 0.15
- Cost tracking aggregation
- **Done when**: 100 tasks x 3 modes scored, reproducibility report generated
- **Informed by**: Riskiest-First, Demo-able

### Phase 7: Analysis & reporting

- Score distributions per suite/difficulty/mode
- MCP benefit delta calculations
- Calibration bias check
- Reproducibility stats
- Visualization pipeline
- **Done when**: Complete analysis report with charts and statistical tests
- **Informed by**: All strategies

### Phase 8: Paper & packaging

- Benchmark paper (methodology, results, analysis)
- External release packaging
- Documentation and setup guide
- **Done when**: Paper draft complete, release artifacts packaged
- **Informed by**: All strategies (terminal)

## Key Risks

| Risk                                         | Impact | Mitigation                                                      |
| -------------------------------------------- | ------ | --------------------------------------------------------------- |
| Session-chain handoff fails under real agent | High   | Phase 1 isolates this cheaply                                   |
| MCP endpoint unreachable from sandboxes      | High   | Phase 2 proves this early with 1 task                           |
| High fraction of 88 tasks are broken         | High   | Two-batch approach; dry-run validation pass                     |
| Three-mode comparison shows no MCP delta     | High   | Valid finding; pivot paper to characterize when/where MCP helps |
| Reproducibility variance > 0.15              | High   | Report honestly; identify variance sources                      |
| Full sweep cost exceeds budget               | Medium | Stratified sample for 3-mode; baseline-only for rest            |

## Dependency Graph

```
Phase 1 (session types) ──┐
                          ├──> Phase 4 (first half tasks) ──> Phase 5 (ground truth)
Phase 2 (3-mode proof) ───┤                                       │
                          │                                        v
Phase 3 (eb_verify) ──────┘                              Phase 6 (complete sweep)
                                                                   │
                                                                   v
                                                          Phase 7 (analysis)
                                                                   │
                                                                   v
                                                          Phase 8 (paper)
```
