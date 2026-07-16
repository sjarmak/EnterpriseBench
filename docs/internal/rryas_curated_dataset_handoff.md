# Handoff: rryas curated-dataset selection

**Epic:** `EnterpriseBench-rryas` — clean MCP vs baseline vs CLI headline study.
**This task:** pick the *best curated subset* of tasks for the 3-arm run (the epic
says "do not run on the full noisy corpus"). Owner of arm/guard design is EB PL;
this handoff is the dataset half.

**Status when written (2026-07-15):** the 3-arm harness is validated end-to-end.
The shakeout (`rryas.1`) ran 8/9 valid across baseline/mcp_only/cli on 3
calibration tasks; all three arms authenticate off the live `.env.local` token
and are cleanly distinct (baseline touches no tool, mcp_only only MCP, cli only
sgx). The dataset is the last thing between here and the headline run.

## The one lesson that drives selection

On `technical_debt/calibration-001` (single local repo, dead-code audit) the cli
agent did 41 turns of real work but made **0 sgx calls** — it solved the task
with local grep/read and never needed retrieval, so the run was correctly gated
`infra_sgx_unused`. **A task where local tools suffice cannot separate the arms.**

Therefore the primary filter is **retrieval necessity**: multi-repo tasks where
every declared repo is structurally required. Single-local-repo tasks are out
unless the repo is large/complex enough that local search is impractical (justify
per task; default is exclude).

## Candidate pool (executable, reproducible)

```bash
python3 scripts/validation/curated_candidate_pool.py          # 122 tasks, table
python3 scripts/validation/curated_candidate_pool.py --json   # machine-readable
python3 scripts/validation/curated_candidate_pool.py --min-repos 3   # 29 strongest
```

As of this writing: **122 CRNT-passing multi-repo candidates** (180 active tasks
scanned). Distribution:
- stratum: dual_repo 92, tri_repo 19, multi_repo 11
- type: support_code_mapping 28, dependency_graph 25, incident_investigation 20,
  error_provenance 12, api_contract 10, config_drift 9, refactor_orchestration 9,
  dead_code_necropsy 5, db_schema_evolution 4
- suite: customer_escalation 40, dependency_management 35, incident_response 20,
  technical_debt 14, platform_engineering 9, feature_delivery 4

The `--min-repos 3` view (29 tasks, mostly dependency_graph) is the strongest
retrieval-forcing subset — good backbone, but broaden across types so the
headline is not a dependency-graph benchmark in disguise.

## Selection gate (apply in order)

1. **Retrieval necessity (structural, done):** in the CRNT pool above.
2. **mcp_only-answerable (hard):** the mcp_only arm builds the sg-only image with
   an EMPTY `/workspace` (no local clones). The task must be solvable from remote
   retrieval alone. Reject any task whose ground truth needs a local artifact the
   remote index doesn't serve (build outputs, generated files, runtime state).
   Verify by reading `ground_truth.required_files` / `sufficient_files` — are they
   all source files a Sourcegraph mirror indexes?
3. **Prompt-echo resistant scoring (hard):** the checks must not credit an echo of
   the prompt. The dep-traversal family was just re-anchored to non-prompt evidence
   (`vjrbw`, `jn73.2.7.3`); `tests/integrity/test_dep_traversal_prompt_echo.py`
   is the template. For each candidate, confirm a covering negative vector exists
   or add one: `cp instruction.md <deliverable>` and any prompt-vocabulary answer
   must score 0. `security_operations/rbac-audit-001`,
   `feature_delivery/camel-routing-arch-001`,
   `security_operations/ceph-rgw-auth-secure-001` are KNOWN partial-echo tasks
   (tracked under `jn73.2.7.3`) — fix or exclude before including.
4. **Deterministic, reliable checks:** prefer tasks scored by the eb_verify
   plugins with stable checkpoints. Spot-run each candidate's checks on its
   `expected_solution.json` — it should pass every checkpoint (internal
   consistency), exactly as the dep-traversal test asserts.
5. **Diversity (soft):** span task types and strata; hit the PRD task-mix targets
   (`python3 scripts/validation/task_mix_validator.py`). Avoid overloading one
   suite/type.

## Empirical validation gate (before locking the set)

Structural filters are necessary, not sufficient. Run a **mini 3-arm pilot** on
the shortlisted candidates (baseline/mcp_only/cli, mode-suffixed, parallel across
non-rate-limited accounts) and keep only tasks that show arm separation:

- **cli/mcp_only actually use their tool:** `sgx_tool_calls > 0` / `mcp_tool_calls
  > 0`. A task that gets 0 (like technical_debt/cal-001) is out — the agent solved
  it another way.
- **baseline does not trivially win:** if baseline scores as high as the retrieval
  arms, the task does not exercise retrieval and adds no signal.
- **no confounds:** valid runs only (watch the failure_class column). Rate-limited
  runs now route to `infra_rate_limit` (`rryas.7`) and are re-runnable — use a
  fresh account, not account2 during its limit window.

Harness invocation (single task, one arm):
```bash
python3 scripts/orchestration/run_task.py benchmarks/<suite>/<task>/task.toml \
  --mode {baseline|mcp_only|cli} --account <N> --output-dir results/runs/<...>
```
`run_task.py` is single-task; parallelize in the caller (see the shakeout
orchestrator pattern: waves of 3, distinct accounts, RAM ~8GB/container). The
token loads from `.env.local` automatically (no shell export needed). Accounts
live at `~/.claude-homes/account{1..5}`; **account tokens are valid but some hit
session limits** — check with a live run, not `_load_oauth_token` (that only
tests expiry).

## Target size

Aim for a curated set large enough for a credible headline yet small enough to
run 3x (one per arm) with repeats under the account budget. A practical first cut:
~30-40 tasks, type-balanced, tri/multi-repo-weighted, each passing gates 1-5 and
the empirical pilot. Confirm with EB PL before locking.

## Open dependencies / watch-outs

- **Arm-image guards (7rc1):** the epic mandates build-time image enforcement
  (mcp_only builds an empty-`/workspace` sg-only image, per-arm build assert,
  per-trial image DIGEST recorded in results.json). Confirm this is live on main
  before the headline run — a curated set is worthless if the arms rebuild the
  same standard image. (Prior confound: all arms were byte-identical baseline
  images.) Verify the mcp_only run's `/workspace` is actually empty and the digest
  is recorded.
- **Account rate limits:** only account2 was session-limited during the shakeout
  (reset 12:40am UTC); 1/3/4/5 were live. Budget the pilot + headline around this;
  `infra_rate_limit` runs are re-runnable on a fresh account.
- **Prompt-echo debt:** `jn73.2.7.3` still open for the 3 non-dep-traversal
  partial-echo tasks. Do not include them until fixed.

## Pointers

- Selection tool: `scripts/validation/curated_candidate_pool.py`
- CRNT rule: `scripts/validation/crnt_validator.py`
- Task-mix targets: `scripts/validation/task_mix_validator.py`
- Prompt-echo test template: `tests/integrity/test_dep_traversal_prompt_echo.py`
- Shakeout results: `results/runs/rryas_shakeout/`
- Harness: `scripts/orchestration/run_task.py`; arm gates: `_route_zero_mcp_run`,
  `_route_zero_sgx_run`, `_verify_mcp_endpoint`, `_verify_sgx_endpoint`,
  `_route_agent_exit`
