---
name: eb-crnt-and-task-mix
description: >
  Cross-Repo Necessity Test (CRNT) and PRD task-mix targets for
  EnterpriseBench. Load when authoring or reviewing a multi-repo task, when
  running or interpreting make verify / verify-mix / verify-crnt, when
  crnt_validator.py or task_mix_validator.py or ecosystem_cap_gate.py fails,
  when a task is suspected of being "window dressing" (a declared repo the
  agent never needs), when adding a Go-tagged task near the 40% ecosystem cap,
  when planning CRNT ablation runs (run_crnt_ablation.sh, verify_grounding.py),
  or when deciding whether a task counts as strict vs broad multi-repo.
---

# CRNT and Task-Mix Targets

This skill covers the two corpus-level quality gates on EnterpriseBench's
task set: the **Cross-Repo Necessity Test (CRNT)** — does a multi-repo task
genuinely require every repo it declares? — and the **PRD task-mix targets** —
is the corpus as a whole balanced across strata, task types, and ecosystems?
Both have executable validators under `scripts/validation/`.

**When NOT to use this skill.** Route elsewhere for:

| You are doing                                                           | Use sibling               |
| ----------------------------------------------------------------------- | ------------------------- |
| Writing a new task.toml, checkpoints, instruction.md, expected_solution | `eb-task-authoring`       |
| Understanding how checkpoint scores become numbers                      | `eb-checkpoint-scoring`   |
| Artifact validators in `lib/eb_verify/`                                 | `eb-verification-library` |
| Running a task in Docker (which ablation runs require)                  | `eb-sandbox-execution`    |
| CI vs local test parity, `pip install -e lib/`                          | `eb-build-and-test`       |
| Running campaigns and analyzing results                                 | `eb-run-and-analyze`      |
| First contact with the repo                                             | `eb-orientation`          |

Jargon used below, defined once:

- **Task** — one directory `benchmarks/<suite>/<task-id>/` with a `task.toml`.
  "Active" = not under `benchmarks/_archived/`. (`benchmarks/mined/` holds
  candidate lists, not `task.toml` files, so it never enters the counts —
  verified 2026-07-07.)
- **Difficulty stratum** — top-level `difficulty_stratum` field in task.toml:
  `calibration | large_single | dual_repo | tri_repo | multi_repo |
monorepo_cross_package`.
- **Strict multi-repo** — stratum in {`dual_repo`, `tri_repo`, `multi_repo`}.
- **Broad multi-repo** — strict plus `monorepo_cross_package`.
- **Ecosystem label** — the union of `metadata.languages` and
  `metadata.frameworks` in task.toml. A task tagged `languages = ["go"]`,
  `frameworks = ["k8s"]` counts once toward `go` and once toward `k8s`.
- **Decorative repo** — a repo listed in `[[repos]]` that the agent does not
  actually need to answer the task. CRNT exists to catch these.
- **Ablation** — re-running a task with one declared repo removed from the
  sandbox, to measure whether the score drops.

---

## 1. CRNT — doctrine vs. what is implemented

CRNT came out of the task-mix convergence debate
(`docs/CONVERGENCE_REPORT_TASK_MIX.md`) as a three-criterion standard applied
to ALL multi-repo tasks, converted or net-new:

| #   | Criterion                                                                                                                                              | Enforcement today (2026-07-07)                                                                                                            |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | **Information asymmetry** — the answer requires facts from 2+ repos not found in any single repo                                                       | Design-review judgment. Not automated.                                                                                                    |
| 2   | **Structural grounding** — every declared repo is anchored in ground truth                                                                             | Automated: `scripts/validation/crnt_validator.py` checks every repo has ≥1 `ground_truth.required_files` entry                            |
| 3   | **Ablation validation** — remove one repo; agent score must drop (PRD acceptance: to ≤60% of checkpoints, `docs/internal/prd_task_mix_realignment.md`) | Semi-automated: `scripts/validation/run_crnt_ablation.sh` runs the ablations; `scripts/validation/verify_grounding.py` checks the results |

History you need to not re-fight: criterion 2 was originally "at least one
_checkpoint_ anchored in each repo" via per-checkpoint `repo_deps` metadata.
That was removed on 2026-04-04 (commit `73ae03d`, "simplify CRNT to structural
check, remove repo_deps") because it conflated "where the answer lives" with
"what context you need to find it," and pilot data showed repo-anchored
checkpoints penalized MCP modes without measuring cross-repo capability.
Do not reintroduce per-checkpoint repo attribution; the settled design is
required_files distribution + empirical ablation.

**Known gap (open, 2026-07-07):** the PRD acceptance threshold for criterion 3
is "ablated score ≤60%", but `verify_grounding.py` implements only
`ablated < 1.0` — _any_ degradation counts as grounded
(`scripts/validation/verify_grounding.py:62-67`). Treat a task whose ablated
score barely drops as suspect even if the tool says "grounded". The 60%
threshold has not been codified anywhere executable.

### 1a. Run the structural CRNT check (fast, no Docker)

Per task, from the repo root:

```bash
python3 scripts/validation/crnt_validator.py benchmarks/dependency_management/dep-mgmt-etcd-grpc-001/task.toml
python3 scripts/validation/crnt_validator.py <path>/task.toml --json   # machine-readable
```

Exit codes (verified against `crnt_validator.py:main`):

| Exit | Meaning                                                                                                                            |
| ---- | ---------------------------------------------------------------------------------------------------------------------------------- |
| 0    | PASS — every declared repo has ≥1 required_files entry — **or** the task has <2 repos (CRNT does not apply; prints a skip message) |
| 1    | Validator error (task.toml not found)                                                                                              |
| 2    | FAIL — at least one repo has zero required_files entries (they are listed)                                                         |

A FAIL prints exactly which repos are uncovered:

```
CRNT FAIL: api-contract-grpc-transport-003 (3 repos)

  etcd                 required_files=0 [MISSING]
  grpc-go              required_files=5 [ok]
  kubernetes           required_files=0 [MISSING]
```

The fix is never "delete the repo from task.toml to make CRNT pass" — that may
be right for a genuinely decorative repo, but it changes the task's stratum
and the corpus mix. First determine whether the repo is needed (criterion 1);
if yes, add real `ground_truth.required_files` entries for it (schema:
`schemas/task.schema.json`, `ground_truth.required_files[]` requires `path`
and `repo`); if no, removing it is a task-mix-affecting change — see §4.

### 1b. TRAP: `make verify-crnt` is broken (2026-07-07)

The Makefile target passes no argument, but the validator requires one:

```
$ make verify-crnt
crnt_validator.py: error: the following arguments are required: task_toml
make: *** [Makefile:46: verify-crnt] Error 2
```

Consequence: **`make verify` (= verify-mix + verify-tasks + verify-crnt)
always fails at the last step**, regardless of corpus health. Note CI
(`.github/workflows/ci.yml`) never calls `make verify` — the CI gates are
pytest + `scripts/audit_consistency.py` + `bash -n` on benchmark shell
scripts — so this breakage does not block merges; it silently means
**no corpus-wide CRNT sweep runs anywhere automatically**.

Use the shipped read-only sweep instead:

```bash
.claude/skills/eb-crnt-and-task-mix/scripts/crnt_all.sh
```

It loops the validator over every active task.toml, prints one line per
failure, and exits 1 if any task fails. Fixing the Makefile target itself is a
real repair (it needs a loop like the script's), but it touches the verify
gate — treat as gated work, see §4.

**Current state (working tree, 2026-07-07): 7 of 180 active tasks FAIL the
structural CRNT**, including tasks committed on `main`:
`api-contract-003/-004/-006/-007` (dependency_management),
`incident-investigation-003` (incident_response),
`refactor-orchestration-007/-008` (technical_debt). These are open corpus
defects, not validator bugs — each has declared repos with zero
required_files. Do not "fix" them casually; repo-list or ground-truth edits
to existing tasks are gated (§4).

### 1c. Empirical ablation (criterion 3) — Docker, slow, costs agent runs

`run_crnt_ablation.sh` builds one ablated image per declared repo (that repo
removed from the sandbox), runs the agent against each, and writes results
under the standard layout with `ablate-<excluded_repo>` as the mode:

```bash
scripts/validation/run_crnt_ablation.sh benchmarks/<suite>/<task-id>/ --dry-run   # ALWAYS dry-run first
scripts/validation/run_crnt_ablation.sh benchmarks/<suite>/<task-id>/ --reps 5
scripts/validation/run_crnt_ablation.sh benchmarks/<suite>/<task-id>/ --repo etcd --mode baseline
# → results/runs/<task_id>/ablate-<excluded_repo>/rep<N>/
```

Options (from `--help`): `--reps N` (default 3), `--mode baseline|mcp_only|hybrid`
(default baseline), `--repo REPO` (ablate one repo only), `--dry-run`. This
launches real Docker builds and real agent sessions — it is a benchmark run,
not a lint. Sandbox mechanics: `eb-sandbox-execution`.

Then score the grounding:

```bash
python3 scripts/validation/verify_grounding.py benchmarks/<suite>/<task-id>/ \
    --results-dir results/runs/<task-id>/
```

Without `--results-dir` it degrades to the static required_files check.
`crnt_validator.py --output-dir <dir>` is a related utility: it writes one
ablated task-config JSON per repo (used by the ablation tooling).

Lessons from the Phase-1 pilot ablations (`docs/phase1_pilot_analysis.md`,
"Ablation Conclusions") — read these before trusting your ablation numbers:

1. **Instruction-context leakage**: agents sometimes score well with a repo
   removed because `instruction.md` embeds file paths / function names /
   domain facts. If the ablated score stays high, check the instruction before
   blaming the repo. Do not embed specific paths or symbol names in
   instructions for new tasks.
2. **Variance**: n=3 reps produced volatile results (0.0 / 0.0 / 4.0 on one
   task). Use `--reps 5` for decisions.
3. A near-zero score drop for one repo ("grafana-dominance" in the pilot)
   means the investigation path is effectively single-repo even if structure
   passes — that is a criterion-1 failure.

---

## 2. Task-mix targets and `task_mix_validator.py`

`docs/benchmark_design.md` is the canonical machine-checked statement of the
corpus constraints. Three targets are enforced by
`scripts/validation/task_mix_validator.py` (constants at
`task_mix_validator.py:34-58`):

| Target                            | Value                                                 | Enforced how                                                                                                                                     |
| --------------------------------- | ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| Strict multi-repo share           | ≥ 45% of all active tasks                             | `MIN_STRICT_MULTI_REPO_PCT = 0.45`                                                                                                               |
| Multi-repo variants per task type | ≥ 2 for each of the 10 task types                     | `MIN_MULTI_REPO_PER_TYPE = 2` (per-type counts use **broad** multi-repo, i.e. monorepo_cross_package counts)                                     |
| Single-ecosystem cap              | ≤ 40% of multi-repo tasks for any one ecosystem label | `MAX_SINGLE_ECOSYSTEM_PCT = 0.40` (denominator: broad multi-repo task count; a task with k labels contributes to k buckets, so shares sum >100%) |

The 10 task types (validator's `EXPECTED_TASK_TYPES`): api_contract,
config_drift, db_schema_evolution, dead_code_necropsy, dependency_graph,
error_provenance, incident_investigation, monorepo_boundary,
refactor_orchestration, support_code_mapping.

Run it:

```bash
python3 scripts/validation/task_mix_validator.py          # human report; exit 0 pass / 1 fail
python3 scripts/validation/task_mix_validator.py --json   # machine-readable
make verify-mix                                           # same thing
```

The report also prints **report-only** metrics that no gate enforces:
stratum distribution, per-type multi-repo %, full ecosystem table, and the
"investigate pattern" share. PRD Should-Haves that are **not** validator-
enforced (do not claim they are): ≥55% broad multi-repo, ≥5 ecosystem chains,
≥40% of _new_ tasks using the `investigate` pattern
(`docs/internal/prd_task_mix_realignment.md`, Should-Have section). Dual-track
reporting (strict AND broad percentages) is the settled convention — report
both, never argue the monorepo denominator.

Snapshot, working tree 2026-07-07 (volatile — re-run, don't trust):
180 active tasks; strict multi-repo 129/180 = 71.7% PASS; all 10 types ≥2
PASS; max ecosystem `go` at 39.7% of 141 multi-repo tasks — PASS but **0.3
points under the cap**. Strata: dual_repo 94, large_single 25, tri_repo 21,
calibration 14, multi_repo 14, monorepo_cross_package 12. Investigate pattern
91/141 (64.5%). Beware: the working tree carried ~64 uncommitted new tasks —
`git ls-tree -r HEAD --name-only benchmarks/ | grep task.toml | grep -vc
_archived` gave **116 active at HEAD** vs 180 in the tree, and CLAUDE.md's
"112 active tasks" is stale. The validator measures the working tree.

---

## 3. The ecosystem cap gate (`ecosystem_cap_gate.py`)

The mix validator's 40% cap is **descriptive** (is the corpus in balance
now?). `scripts/validation/ecosystem_cap_gate.py` is **prescriptive**: it
compares baseline (default `HEAD`) vs candidate (default working tree) and
blocks changes that make a capped ecosystem _worse_. Capped ecosystems:
`DEFAULT_CAPS = {"go": 0.40}` (`ecosystem_cap_gate.py:74`) — only Go today.

```bash
python3 scripts/validation/ecosystem_cap_gate.py            # working tree vs HEAD
python3 scripts/validation/ecosystem_cap_gate.py --json
python3 scripts/validation/ecosystem_cap_gate.py --baseline-ref HEAD~1
python3 scripts/validation/ecosystem_cap_gate.py --caps 'go=0.40,python=0.30'
# exit 0 pass, non-zero on violation (2 for a malformed --caps string)
```

Block/pass logic keys on **share, not raw count** (full table in
`docs/benchmark_design.md`): over-cap-and-rising blocks; over-cap-but-falling
passes (so a batch that adds a few Go tasks among many non-Go tasks is fine);
under-cap on both sides passes. The gate exists because of a real incident:
on 2026-04-28, eleven Go-tagged dual-repo incident-investigation tasks landed
during an active Go-balance correction and pushed multi-repo Go% from 40.7% to
46.2% (`docs/audits/go_balance_audit_2026_04.md`). The audit found none of the
11 `go` tags removable, so recovery required authoring non-Go tasks. If your
Go-tagged task is blocked: land it together with non-Go tasks that keep Go's
share flat, or wait for balance, or drop the `go` tag only if the task is
genuinely not Go-essential (0 of 11 qualified in the audit).

**Doc-drift warning (verified 2026-07-07):** `docs/benchmark_design.md` claims
the gate is wired to `make verify-ecosystem-gate` and "a CI job in
`.github/workflows/ci.yml`". **Neither exists** — the Makefile has no such
target and ci.yml has no gate step. Until that lands, the gate only runs when
you run it. Run it manually before committing any task add/remove/re-tag.

Related read-only diagnostic:
`python3 scripts/validation/ecosystem_diversity_report.py [--threshold 25]` —
repo_set_id concentration report, no gating.

---

## 4. Pre-commit checklist and change control

Before committing any change that adds, removes, re-strata-fies, re-tags, or
edits the repo list / ground truth of a task (repo root):

```bash
python3 scripts/validation/task_mix_validator.py                       # corpus targets
python3 scripts/validation/ecosystem_cap_gate.py                       # no worsening of go%
.claude/skills/eb-crnt-and-task-mix/scripts/crnt_all.sh                # structural CRNT sweep
python3 scripts/validate_tasks_preflight.py --task-id <your-task-id>   # schema/preflight (see eb-task-authoring)
python3 scripts/audit_consistency.py                                   # the actual CI blocker
```

For a NEW multi-repo task the full CRNT quality gate per the convergence
report is: structural pass + ablation pass + ≥1 MCP-mode evaluation run.
Structural alone is necessary, not sufficient.

Standing rules (each with its source):

- **Replace-before-cut** (`docs/CONVERGENCE_REPORT_TASK_MIX.md` §1): never
  retire a single-repo task until its multi-repo replacement passes CRNT and
  has at least one MCP-mode evaluation run.
- **Thresholds live in the PRD, not the validator.** `MIN_STRICT_MULTI_REPO_PCT`,
  `MIN_MULTI_REPO_PER_TYPE`, `MAX_SINGLE_ECOSYSTEM_PCT`, and `DEFAULT_CAPS`
  encode debated PRD decisions (`docs/CONVERGENCE_REPORT_TASK_MIX.md`,
  `docs/internal/prd_task_mix_realignment.md`). Editing a constant to make a
  red gate green is routing around change control.
- **PROVISIONAL pending Stephanie (discovery Q5):** treat task-mix changes —
  retirements, stratum reclassification, ecosystem re-tagging, cap/threshold
  edits, grading-keyword relaxations — as HALT-branch-ready: stop at a ready
  branch with tests and get Stephanie's sign-off before landing. This
  conservative gate mirrors the production-scoring-path rule and stands until
  she says otherwise.
- **PROVISIONAL pending Stephanie (discovery Q5):** the 28 archived
  single-repo tasks and the 3 cut coding-ability tasks
  (beam-pipeline-builder-refac-001, ansible-abc-imports-fix-001,
  aspnetcore-code-review-001) are parked-not-dead. Check the work queue and
  branch state before re-landing or re-using anything from
  `benchmarks/_archived/`.

Unit tests for this machinery (run in CI): `tests/test_crnt_validator.py`
(31 tests) and `tests/test_ecosystem_cap_gate.py`. CI runs the unit tests but
NOT the corpus-level sweeps — a task can merge while failing structural CRNT,
which is exactly how the 7 failures in §1b exist on `main`.

---

## Provenance and maintenance

Authored 2026-07-07 against the working tree at commit `7cfb8b0` (branch
`main`) of the EnterpriseBench repo, retiring-fellow campaign. Written
repo-portable per the campaign's Q1 provisional position (no user-machine
paths as load-bearing sources). Every command above was executed this session.
Volatile facts and their one-line re-verification commands:

| Claim                                               | Re-verify with                                                                            |
| --------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `make verify-crnt` broken (no positional arg)       | `make verify-crnt` — fixed once it exits 0 or fails per-task                              |
| 7 active tasks fail structural CRNT                 | `.claude/skills/eb-crnt-and-task-mix/scripts/crnt_all.sh`                                 |
| Mix targets + thresholds (45% / 2-per-type / 40%)   | `sed -n '30,60p' scripts/validation/task_mix_validator.py` and `docs/benchmark_design.md` |
| Corpus snapshot (180 tasks, go 39.7%)               | `python3 scripts/validation/task_mix_validator.py \| tail -15`                            |
| Active-at-HEAD vs working-tree count                | `git ls-tree -r HEAD --name-only benchmarks/ \| grep task.toml$ \| grep -vc _archived`    |
| No `verify-ecosystem-gate` target / no CI gate step | `grep -n ecosystem Makefile .github/workflows/ci.yml`                                     |
| Cap set (go only, 0.40)                             | `grep -n DEFAULT_CAPS scripts/validation/ecosystem_cap_gate.py`                           |
| verify_grounding threshold still `< 1.0` not ≤60%   | `grep -n 'ablated < 1.0' scripts/validation/verify_grounding.py`                          |
| CRNT structural-check design (repo_deps removed)    | `git log --oneline --follow scripts/validation/crnt_validator.py`                         |
| CI does not run `make verify`                       | `cat .github/workflows/ci.yml`                                                            |
