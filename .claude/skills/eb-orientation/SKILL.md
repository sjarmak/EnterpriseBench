---
name: eb-orientation
description: >
  Load FIRST in any EnterpriseBench session where you lack context: what the
  benchmark is, the CodeScaleBench (CSB) lineage, the suite/type/stratum task
  taxonomy and where the LIVE task counts come from, the two-axis verification
  model (checkpoint scoring + artifact validation), which root directories are
  real source vs stale agent worktrees, and the ordered reading route for a
  newcomer. Triggers: "what is EnterpriseBench", "how is this repo organized",
  "how many tasks are there", "what are the task types/suites", "where do I
  start", "which directories matter", "what is CSB", "how does verification
  work at a high level", or any task where you are about to explore the repo
  from scratch.
---

# EnterpriseBench Orientation — The Map

This skill is the map, not the terrain. It tells you what EnterpriseBench is,
how it is laid out, where the live numbers come from, and what to read in what
order. It deliberately does NOT teach you how to score, author, or run tasks.

**When NOT to use this skill — sibling routing table:**

| You need to...                                                                 | Load instead                                                        |
| ------------------------------------------------------------------------------ | ------------------------------------------------------------------- |
| Change or reason about anything on the scoring path                            | `eb-scoring-integrity-doctrine` (read it BEFORE any scoring change) |
| Work inside `lib/eb_verify/` (validators, plugins, groundedness)               | `eb-verification-library`                                           |
| Understand how a checkpoint becomes a number (weights, judge cap, two scorers) | `eb-checkpoint-scoring`                                             |
| Add or fix a task (`task.toml`, checkpoints, ground truth)                     | `eb-task-authoring`                                                 |
| Pass CRNT or the task-mix gate                                                 | `eb-crnt-and-task-mix`                                              |
| Run one task in Docker / debug the sandbox                                     | `eb-sandbox-execution`                                              |
| Configure baseline / mcp_only / hybrid modes                                   | `eb-mcp-modes`                                                      |
| Provision or debug Sourcegraph `sg-evals` mirrors                              | `eb-sourcegraph-mirrors`                                            |
| Get tests green the way CI is green                                            | `eb-build-and-test`                                                 |
| Run a benchmark campaign and produce figures                                   | `eb-run-and-analyze`                                                |
| Use chain / event_replay / resume sessions                                     | `eb-session-types`                                                  |
| Branch, dispatch, or land a change in this rig                                 | `eb-git-and-dispatch-workflow` (internal-orchestration)             |
| Work on the scorer_guard consolidation                                         | `eb-scorer-guard-campaign`                                          |

---

## 1. What EnterpriseBench is (60 seconds)

EnterpriseBench is a **benchmark**, written in Python, that measures how well
coding agents **find and comprehend the right code across large, multi-repo
enterprise codebases**. It is NOT a code-generation benchmark: the primary
measurement is context retrieval quality (which files/lines the agent found
and used), and tasks produce diverse artifacts — structured answers, incident
reports, runbooks, call graphs, configs — not only patches.

Three facts shape everything:

1. **Tool access is the controlled independent variable.** Every task can run
   in three modes: `baseline` (local tools only), `mcp_only` (Sourcegraph MCP
   only), `hybrid` (both). Sourcegraph MCP is the first-class showcase, but
   the benchmark's job is to _measure_ whether MCP lifts performance, not to
   assume it does. Details: `eb-mcp-modes`.
2. **The central deliverable is a verification pipeline that survives a
   skeptic.** A benchmark is only worth its numbers, and the numbers are only
   worth the scorer's trustworthiness. The single most damaging thing a
   newcomer can do here is introduce a silent mis-score. Before touching
   anything that produces or transforms a score, read
   `eb-scoring-integrity-doctrine`.
3. **It is on a publication track.** `paper/paper.md` is hand-written;
   `make paper-figures` regenerates every figure from raw run data. Claims in
   external prose must never outrun the artifacts under `results/`.

Repos used in tasks are **real OSS only**, pinned by SHA/tag in
`configs/repo_versions.json`, connected by genuine dependency chains
(e.g. `grpc-go -> etcd -> kubernetes`). In the sandbox, each task's repos are
cloned into `/workspace/{repo-name}/`.

License: Apache 2.0. CI: GitHub Actions, Python 3.12
(`.github/workflows/ci.yml`).

## 2. CSB lineage — where this came from

EnterpriseBench is the evolution of **CodeScaleBench (CSB)**, an unpublished
predecessor. Per the repo's own docs (`CLAUDE.md`, `docs/ARCHITECTURE.md`;
CSB itself is not in this repo, so these figures are inherited, not
re-countable here):

- CSB had **275 tasks (220 Org + 55 SDLC)**; the standing doctrine is
  "fix, extend, don't rebuild" — CSB infrastructure carries forward.
- **178 `sg-evals` Sourcegraph mirrors** came from CSB and were extended for
  multi-repo tasks. The live indexing manifest is
  `configs/sg_indexing_list.json` (as of its `_generated` stamp 2026-07-05:
  133 unique repos, 114 mirror files — see `eb-sourcegraph-mirrors` before
  drawing conclusions from the 178-vs-133 gap).
- CSB's SDLC/Org task split was replaced by the **7 enterprise workflow
  suites** (mapping in `docs/taxonomy_mapping.md`).
- Legacy-task debt was assessed in `docs/LEGACY_CSB_ASSESSMENT.md` (13 legacy
  tasks scored against current standards, 2026-03-28) and CSB's known bugs are
  chronicled in `docs/csb_bugs.md`.
- `scripts/migrate_csb_task.py` is the migration tool for carrying a CSB task
  forward.

Jargon defined once: **suite** = enterprise workflow cluster a task belongs
to; **task type** = the kind of comprehension work (one of 10); **stratum** =
the repo-count difficulty band; **CRNT** = Cross-Repo Necessity Test, the gate
proving a multi-repo task genuinely requires crossing repos; **checkpoint** =
one graduated, independently verified step of a task; **artifact validator** =
an `eb_verify` plugin that checks one artifact type; **sg-evals mirrors** =
GitHub mirror repos indexed by Sourcegraph so MCP modes can search pinned
code.

## 3. Task taxonomy — and where the LIVE counts come from

**Trust the validator, not the prose docs.** README.md, CLAUDE.md, and
`docs/ARCHITECTURE.md` all carry task counts (112 active / "100 tasks" /
28 archived) that are **stale as of 2026-07-07**. The single source of truth
for live counts is:

```bash
python3 scripts/validation/task_mix_validator.py        # human-readable
python3 scripts/validation/task_mix_validator.py --json # machine-readable
```

It scans every non-archived `benchmarks/**/task.toml`. Output on 2026-07-07:
**180 active tasks**, all PRD targets passing (strict multi-repo 71.7%,
all 10 types >= 2 multi-repo variants, no ecosystem > 40%).

**Working-tree caveat:** the 180 is a working-tree census on the maintainer's
machine — only **116 of those task.tomls are tracked at HEAD `7cfb8b0`**; 64
are uncommitted. On a public clone, every count in this section (suites,
strata) is smaller. Check which tree you are in:

```bash
git ls-tree -r HEAD --name-only benchmarks/ | grep 'task.toml$' | grep -vc _archived   # 116 at HEAD
find benchmarks -name task.toml -not -path '*_archived*' | wc -l                       # 180 working tree
```

### The 7 suites (live active counts, 2026-07-07)

| Suite (directory under `benchmarks/`) | Active tasks | Typical work                               |
| ------------------------------------- | -----------: | ------------------------------------------ |
| `customer_escalation`                 |           54 | error_provenance, support_code_mapping     |
| `dependency_management`               |           42 | api_contract, dependency_graph             |
| `incident_response`                   |           26 | incident_investigation                     |
| `technical_debt`                      |           23 | refactor_orchestration, dead_code_necropsy |
| `feature_delivery`                    |           19 | monorepo_boundary, db_schema_evolution     |
| `platform_engineering`                |           14 | config_drift                               |
| `security_operations`                 |            2 | vulnerability / access-control assessment  |

Count any suite yourself:
`find benchmarks/<suite> -maxdepth 2 -name task.toml | wc -l`

### The 10 task types

`api_contract`, `config_drift`, `db_schema_evolution`, `dead_code_necropsy`,
`dependency_graph`, `error_provenance`, `incident_investigation`,
`monorepo_boundary`, `refactor_orchestration`, `support_code_mapping`.

Full definitions with Sourcegraph-MCP signal ratings (5-star scale):
`docs/TASK_TYPE_PRD.md` (98K — read the executive summary, use the rest as a
per-type reference).

### The 6 difficulty strata (live distribution, 2026-07-07)

| Stratum                  | Tasks | Share |
| ------------------------ | ----: | ----: |
| `dual_repo`              |    94 | 52.2% |
| `large_single`           |    25 | 13.9% |
| `tri_repo`               |    21 | 11.7% |
| `calibration`            |    14 |  7.8% |
| `multi_repo` (4-5 repos) |    14 |  7.8% |
| `monorepo_cross_package` |    12 |  6.7% |

`calibration` tasks are small single-repo bias checks: MCP should give ~no
advantage on them. Multi-repo tasks follow four atomic patterns: propagate,
investigate, enforce, orchestrate. Mix targets and their rationale:
`eb-crnt-and-task-mix`.

### Anatomy of one task directory

```
benchmarks/<suite>/<task-id>/
├── task.toml               # metadata: id, suite, task_type, difficulty,
│                           # session_type, prompt, [[repos]], [[checkpoints]]
├── instruction.md          # what the agent actually reads in the sandbox
├── ground_truth.json       # required_files / sufficient_files (+ chunks)
├── expected_solution.json  # reference solution for solve-verification
├── checks/                 # one bash verifier per checkpoint
└── environment/            # sandbox environment inputs
```

Schema: `schemas/task.schema.json` (required per task: `id`, `suite`,
`difficulty`, `session_type`; `session_type` enum: `single`, `chain`,
`event_replay`, `resume` — see `eb-session-types`). Authoring:
`eb-task-authoring`.

### Archived and mined

- `benchmarks/_archived/` — retired tasks, preserved for reference. 31
  `task.toml` files as of 2026-07-07: 28 retired tasks under suite subdirs
  (the number README cites) plus 3 top-level examples/one-offs
  (`chain_example`, `event_replay_example`, `bustub-hyperloglog-impl-001`).
  PROVISIONAL pending Stephanie: treat archived tasks as **parked, not
  dead** — check the bead store and branch state before re-landing or
  deleting anything here.
- `benchmarks/mined/` — mining candidate lists and provenance markdowns plus
  loose candidate `.toml` files. NOT active tasks (no `task.toml` task dirs);
  the mix validator ignores it.

## 4. Two-axis verification — the 60-second model

Every task is verified along two independent axes. Know which axis you are on
before reading any scoring code.

**Axis A — checkpoint scoring (did the agent make progress?).** Each task has
2–5 graduated checkpoints for partial credit. Each checkpoint is a bash
verifier in the task's `checks/` dir that prints a single JSON object:
`{"score": <0.0-1.0>, "passed": <bool>, "detail": "..."}`. Aggregation
happens in TWO places, and they do not agree:

- Production path: `scripts/orchestration/run_task.py` + the in-container
  `scripts/sandbox/test_runner.sh`. At HEAD `7cfb8b0` this is in practice
  **equal-weighted** (declared `task.toml` weights are not emitted as
  `.meta` sidecars) — but the fetched `origin/main` changes this; the
  weighting mechanics and the stale-on-pull warning are owned by
  `eb-checkpoint-scoring` §1–§3.
- Library path: `lib/eb_verify/runner.py::CheckpointRunner` — honors declared
  checkpoint weights and carries the tests, but is invoked only by
  `lib/eb_verify/cli.py` and the test suite, not by production runs.

PROVISIONAL pending Stephanie: whether these consolidate (one scorer / CI
oracle / weight propagation) is an OPEN decision. Teach and edit against
current reality only; a change landed in the library path alone does NOT
change production scores. Full treatment: `eb-checkpoint-scoring`.

**Axis B — artifact validation (is the output well-formed and grounded?).**
`lib/eb_verify/plugins/` is a plugin registry keyed by artifact type. Nine
validators register unconditionally: `answer`, `code_patch`,
`config` (the module is `config_validator.py`, but the registered
artifact_type — the key `get_validator()` accepts — is `config`; CLAUDE.md's
`config_validator` is wrong), `incident_report`, `runbook`,
`security_assessment`, `reproduction_script`, `topological_order`,
`call_graph`. A tenth,
`fact_triples`, registers ONLY if numpy/scikit-learn/jsonschema are
importable — otherwise it self-disables with a `RuntimeWarning` and
`get_validator("fact_triples")` returns `None`. Full treatment:
`eb-verification-library`.

**Ground truth is layered** (docs/ARCHITECTURE.md): Tier 1 deterministic (AST
parsing, import graphs, dependency manifests — no LLM), Tier 2 LLM curator
(semantic relevance, tool-independent — never uses Sourcegraph), Tier 3
solve-verification (a different model attempts the task using only the
curated context). The curator/judge acts as a score _ceiling_, never a floor.

**The doctrine in one line:** a score is valid only if the pristine verifier
ran on real agent output; any infra/verifier/judge failure must surface as an
infra error, never as a silent `0.0` or an inflated score. If any change you
are making could violate that, stop and load `eb-scoring-integrity-doctrine`.

## 5. Source vs worktree — which directories are real

**The repo root is polluted by design.** As of 2026-07-07 the working copy
holds ~105 untracked `enterprisebench-*` directories at the root plus a few
under `.claude/worktrees/` — these are agent worktrees (full stale copies of
the tree, created by orchestration). PROVISIONAL pending Stephanie (Q1
placement): a public clone will not have them; in this working copy, never
read, grep, or count anything through them.

Authority for what is real source:

```bash
git ls-files | cut -d/ -f1 | sort -u
```

Tracked top level (verified 2026-07-07):

| Path                                                                       | What it is                                                                                                                    |
| -------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `benchmarks/`                                                              | Task definitions by suite + `_archived/` + `mined/`                                                                           |
| `lib/eb_verify/`                                                           | THE verification library (installed in every sandbox; one copy, never per-task)                                               |
| `scripts/`                                                                 | `mining/`, `sandbox/`, `orchestration/` (incl. `run_task.py`), `validation/`, `infra/`, plus top-level analysis/audit scripts |
| `schemas/task.schema.json`                                                 | Task definition schema                                                                                                        |
| `configs/`                                                                 | `repo_versions.json` (pinned SHAs), `sg_indexing_list.json`, `sg_mirrors/`, manifests                                         |
| `tests/`                                                                   | Full test tree — the CI gate (NOT `make test`; see `eb-build-and-test`)                                                       |
| `docs/`                                                                    | Docs of record (see reading route)                                                                                            |
| `paper/`                                                                   | `paper.md` (hand-written) + generated `figures/`                                                                              |
| `results/`                                                                 | Analysis outputs, campaign dirs, `sample_runs/`; raw `results/runs/` is gitignored                                            |
| `agents/`, `architecture/`                                                 | Agent configs; LikeC4 architecture model (auto-deployed page)                                                                 |
| `README.md`, `CLAUDE.md`, `AGENTS.md`, `Makefile`, `RELEASE.md`, `LICENSE` | Top-level docs and build entry                                                                                                |
| root `rescore_*.py`, `recompute_headline_*.py`, `aggregate_baseline_*.py`  | One-off audit re-score scripts tied to specific past audits — reference, do not extend                                        |

Local-only (present here, gitignored — absent from a public clone):
`.beads/` (work queue; internal orchestration — see
`eb-git-and-dispatch-workflow`), `.gc-reports/` (weekly deep-audit reports;
the best archaeology source in this working copy), `results/runs/` and
`runs/` (raw run data), `venv/`, `.env*`, generated
`benchmarks/**/environment/Dockerfile*`.

Run-output convention (gitignored but load-bearing):
`results/runs/<task_id>/<mode>/[rep<N>/]` containing `results.json`,
`config.json`, `task_metrics.json`, `agent/`, `verifier/`,
`agent_trace.jsonl`. Promotion to `results/official_runs/` goes through
`scripts/orchestration/run_promotion_orchestrator.py` only
(`docs/RUN_PROMOTION.md`).

Git shape: `main` is squash-merged (172 commits as of 2026-07-07); the real
change history lives in ~35 `fix/eb-*` / `audit/eb-*` branches and the bead
store. PROVISIONAL pending Stephanie: those branches are parked-not-dead;
check branch state before duplicating a fix. Process: `eb-git-and-dispatch-workflow`.

## 6. Reading route — first session, in order

Work through this checklist top to bottom; stop when your task's sibling
skill takes over.

1. [ ] `README.md` — pitch, suites/types tables (counts stale; taxonomy
       right), quickstart. NOTE: the README's `run_task.py --task <id>` example
       is stale — the real CLI takes a positional path:
       `python3 scripts/orchestration/run_task.py benchmarks/<suite>/<task-id>/task.toml --mode baseline`
       (verified against `run_task.py` argparse, 2026-07-07).
2. [ ] `CLAUDE.md` — agent navigation guide; key-files index; conventions
       (always parallelize benchmark runs; real OSS only). Same stale counts.
3. [ ] `docs/ARCHITECTURE.md` — design principles, layered ground truth,
       verification flow, session types, CSB relationship. 8K, read fully.
4. [ ] `docs/TASK_TYPE_PRD.md` — executive summary + the table of 10 types
       with MCP-signal ratings only; return per-type as needed.
5. [ ] One real task directory end-to-end, e.g.
       `benchmarks/customer_escalation/support-mapping-001/` — read `task.toml`,
       `instruction.md`, `ground_truth.json`, and one script in `checks/`.
6. [ ] `lib/eb_verify/plugins/__init__.py` — the registry, `safe_read`
       hardening, and the conditional `fact_triples` registration, in ~140 lines.
7. [ ] Skim `scripts/orchestration/run_task.py` top docstring + argparse
       block (lines ~1830-1960). It is 2016 lines and the repo's churn hotspot;
       do NOT try to read it linearly — `eb-sandbox-execution` maps it.
8. [ ] `Makefile` — `make help` lists every target; note `make verify`
       (= verify-mix + verify-tasks + verify-crnt) is the task-authoring gate and
       `make test` is NOT the CI gate.
9. [ ] `docs/TASK_AUTHORING_GUIDE.md` + `docs/CONVERGENCE_REPORT.md` — only
       when you are about to author or judge design decisions.

Environment sanity before any Python work (details: `eb-build-and-test`):

```bash
pip install -e lib/                       # bare `import eb_verify` fails without this
python3 -c "import eb_verify; print(eb_verify.__name__)"
python3 scripts/validation/task_mix_validator.py   # live task census
```

CI's actual gate, for reference (`.github/workflows/ci.yml`):

```bash
python3 -m pytest tests/ -v --tb=short -m "not network and not docker"
python3 scripts/audit_consistency.py
find benchmarks -name "*.sh" -not -path "*/_archived/*" -exec bash -n {} \;
```

Do not run `pytest tests/` WITHOUT the marker filter — `network`/`docker`
marked tests will hit the network and try to build images.

## 7. Orientation-level traps (one line each; siblings have the depth)

- Editing `lib/eb_verify/runner.py` scoring believing it changes production
  scores — production is `run_task.py` + `test_runner.sh` (`eb-checkpoint-scoring`).
- Any `except: return 0.0` or swallowed error on the scoring path — the
  dominant historical bug class (`eb-scoring-integrity-doctrine`).
- Trusting `make test` (library-only) as the CI gate (`eb-build-and-test`).
- Grepping through the `enterprisebench-*` worktree copies and getting stale
  duplicate hits — always constrain searches to tracked paths (section 5).
- Treating documented oddities as bugs (mcp_only still clones repos locally;
  preflight warnings that fire by design) — check `eb-mcp-modes` /
  `eb-sandbox-execution` before "fixing" them.
- Assuming README/CLAUDE.md task counts are current — run the mix validator.

## Provenance and maintenance

Authored 2026-07-07 against the working copy at that date (branch `main`,
head `7cfb8b0`). Every command and path above was executed or read this
session. Volatile facts and their one-line re-verification commands:

- **180 active tasks (working tree; 116 tracked at HEAD); strata/suite distribution:**
  `python3 scripts/validation/task_mix_validator.py` and
  `git ls-tree -r HEAD --name-only benchmarks/ | grep 'task.toml$' | grep -vc _archived`
- **Per-suite counts:**
  `find benchmarks/<suite> -maxdepth 2 -name task.toml | wc -l`
  (exclude `_archived/` and `mined/` when totalling)
- **31 archived task.toml (28 retired + 3 top-level):**
  `find benchmarks/_archived -name task.toml | wc -l`
- **10 task types (enum):**
  `grep -A13 '"task_type"' schemas/task.schema.json`
- **Session type enum (single/chain/event_replay/resume):**
  `grep -A6 '"session_type"' schemas/task.schema.json`
- **9 unconditional + 1 conditional validator:**
  `python3 -c "import eb_verify.plugins as p; print(sorted(p.list_validators()))"`
  (after `pip install -e lib/`)
- **Checkpoint JSON contract:**
  `head -20 benchmarks/customer_escalation/support-mapping-001/checks/*.sh`
- **Equal-weight default in the production scorer:**
  `grep -n "meta" scripts/sandbox/test_runner.sh`
- **run_task.py CLI shape (positional task_toml, no `--task` flag):**
  `grep -n "add_argument" scripts/orchestration/run_task.py`
- **CI gate contents:**
  `cat .github/workflows/ci.yml`
- **~105 stale worktree dirs at root:**
  `ls -d enterprisebench-* 2>/dev/null | wc -l`
- **`main` commit count 172; ~35 fix/audit branches:**
  `git rev-list --count main` and `git branch -a | grep -c -e fix/eb- -e audit/eb-`
- **sg_indexing_list totals (133 repos / 114 mirror files, generated 2026-07-05):**
  `python3 -c "import json; d=json.load(open('configs/sg_indexing_list.json')); print(d['_total_unique_repos'], d['_total_mirror_files'], d['_generated'])"`
- **README/CLAUDE.md counts stale (112 vs live 180):**
  compare `grep -n "112" README.md CLAUDE.md` with the mix validator output

Inherited-from-docs (not independently countable in this repo): CSB 275 tasks
(220 Org + 55 SDLC), 178 sg-evals mirrors from CSB — source: `CLAUDE.md`,
`docs/ARCHITECTURE.md`.
