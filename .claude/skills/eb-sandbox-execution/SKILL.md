---
name: eb-sandbox-execution
description: >
  Run one EnterpriseBench task end-to-end in its Docker sandbox with
  scripts/orchestration/run_task.py. Load this skill when you need to: execute
  or dry-run a single task; understand or modify Dockerfile generation
  (dockerfile_generator.py, the standard/sg_only/hybrid variants); debug a
  Docker build, container setup, chown/permission, or docker-cp failure;
  interpret image tags (eb-<task_id>-<mode>), container names, failure_class
  values, or status="invalid" runs; trace how /workspace gets populated
  (instruction.md, .verifiers/, test.sh, .eb_verify, .task); or audit the
  fail-loud gates that prevent silent fake-0.0 scores. NOT for: running many
  tasks (eb-run-and-analyze), MCP configuration details (eb-mcp-modes),
  checkpoint/judge scoring semantics (eb-checkpoint-scoring), or writing
  verifiers (eb-task-authoring).
---

# EnterpriseBench sandbox execution: run_task.py end-to-end

`scripts/orchestration/run_task.py` is the production worker that runs ONE
single-session task: it generates a Dockerfile, builds an image, creates a
container, copies task files in, optionally runs a Claude Code agent inside,
scores the result with the in-container `test.sh`, and writes results to
`results/runs/`. This skill is the runbook for that pipeline and its traps.

All facts verified against the repo on 2026-07-07.

## When NOT to use this skill

| You want to...                                                                     | Use instead                                                                                                              |
| ---------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Run a batch/campaign of tasks across accounts                                      | eb-run-and-analyze (`scripts/run_benchmark.py` is the dispatcher; `run_task.py` is the single-task worker)               |
| Understand baseline vs mcp_only vs hybrid, MCP preamble, `.mcp.json` wiring        | eb-mcp-modes                                                                                                             |
| Understand how checkpoints become a score, the two-scorer split, the LLM judge cap | eb-checkpoint-scoring                                                                                                    |
| Write or fix a task's verifiers/checkpoints                                        | eb-task-authoring                                                                                                        |
| The doctrine behind "never record a fake 0.0"                                      | eb-scoring-integrity-doctrine                                                                                            |
| Multi-session tasks (chain/event_replay/resume)                                    | eb-session-types (`run_task.py` REJECTS `session_type != "single"` at parse time and tells you to use `chain_runner.py`) |
| sg-evals mirror naming/provisioning                                                | eb-sourcegraph-mirrors                                                                                                   |

## Glossary

- **Sandbox**: the per-task Docker container. Task repos live at
  `/workspace/{repo-name}/` inside it.
- **Mode**: the tool-access arm — `baseline` (no MCP), `mcp_only`, `hybrid`.
  A controlled independent variable, not a convenience flag.
- **Verifier / checkpoint**: a bash script from the task's `checks/` dir that
  prints `{"score": 0-1, "passed": bool, ...}` JSON.
- **Silent zero / fake 0.0**: an infrastructure failure (unreadable file,
  missing package, broken verifier) recorded as a legitimate score of 0.0.
  This is the project's dominant historical bug class; several gates below
  exist solely to prevent it.
- **`status="invalid"`** (`RUN_STATUS_INVALID`): the run must be RE-RUN, never
  scored. Set by the MCP pre-flight gate, the pre-agent readability gate, and
  the post-agent MCP-config-error scan.

## Quickstart (copy-paste)

Run from the repo root. No `pip install` is needed for run_task.py itself
(it manipulates `sys.path` internally), but use the repo venv when present.

```bash
# Dry run: generate Dockerfile, build image, create container, set up
# workspace, then stop before the agent. The standard smoke test.
python3 scripts/orchestration/run_task.py \
  benchmarks/dependency_management/api-contract-001/task.toml --dry-run

# Full baseline run with a Claude Code agent on OAuth account 1
python3 scripts/orchestration/run_task.py \
  benchmarks/dependency_management/api-contract-001/task.toml \
  --account 1 --mode baseline --rep 1

# MCP arm (requires SOURCEGRAPH_ACCESS_TOKEN; auto-loaded from .env.local)
python3 scripts/orchestration/run_task.py \
  benchmarks/dependency_management/api-contract-001/task.toml \
  --account 2 --mode mcp_only --rep 1

# Debug a failure: keep the container alive afterwards
python3 scripts/orchestration/run_task.py <task.toml> --dry-run --keep-container
```

Full flag reference: `python3 scripts/orchestration/run_task.py --help`.
Notable defaults: `--timeout 1800` (agent), `--build-timeout 1800`,
`--verifier-timeout 600`, `--memory 8192` (MB), `--min-disk-gb 10`.
`--max-concurrent-large` is accepted but NOT enforced (the help text says so).

**Parallelism convention (repo CLAUDE.md):** always run benchmark tasks in
parallel with `&` + `wait` across accounts 1-5, never sequentially.
`run_task.py` is single-task by design; the caller parallelizes.

## Pipeline phases

`run_task(config)` executes these phases; each failure path records a
`failure_class` and saves results before returning or raising.

| Phase           | What happens                                                                                                                             | On failure                                                                                                                    |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| 1 Parse         | `_parse_task`: task.toml parsed, `[task].id` required, `session_type` must be `single`, every `[[repos]]` entry validated                | raises                                                                                                                        |
| Disk pre-flight | `_check_disk_space` on `/var/lib/docker` (or `/`)                                                                                        | `phase=preflight_failed`, `failure_class=infra_disk`. NOTE: an OSError while checking **fails open** (returns True) by design |
| 2 Build         | `_generate_dockerfile` + `docker build`                                                                                                  | `phase=build_failed`, `failure_class=infra_build`; "No space left on device" detected specially                               |
| 3 Setup         | `docker create` (memory + 2x swap limit, `sleep infinity`) → `docker start` → `_setup_container` copies task files in                    | `phase=setup_failed`, `failure_class=infra_clone`                                                                             |
| Health check    | `_run_health_check`: `test -d /workspace/<repo>/.git` per repo. **Failure only logs a warning and CONTINUES** — it is not a gate         | warning only                                                                                                                  |
| MCP config      | mcp_only/hybrid only: `_configure_mcp` — HARD gate                                                                                       | `phase=mcp_infra_error`, `status=invalid`, `failure_class=infra_mcp_preflight`                                                |
| 4 Agent         | readability gate → `docker exec -u agent ... <agent_command> < /workspace/instruction.md`                                                | exit 137 → `infra_oom`; exit 124 → `infra_timeout`; other nonzero → `agent_error`                                             |
| 5 Score         | `_run_scoring` runs `bash /workspace/test.sh` with `WORKSPACE`, `TASK_DIR=/workspace/.task`, `PYTHONPATH=/workspace/.eb_verify` exported | see "Known live gaps" below                                                                                                   |
| 5b Judge        | if task declares `verification_modes = ["llm_curator", ...]`: `_apply_llm_judge` caps grep scores at `min(grep, judge)`                  | `verifier_infra_error` only on the no-agent-output branch (see gaps)                                                          |
| 6 Cleanup       | `finally:` stops and removes the container unless `--keep-container`                                                                     | —                                                                                                                             |

Note the parenthetical in run_task.py's own comments: `run_task.py only
handles single-session tasks`; `chain_runner.py` handles chains.

## Dockerfile generation and multi-repo clone-in-build

`scripts/sandbox/dockerfile_generator.py::generate_for_task(task_toml,
source=...)` writes THREE variants into `<task_dir>/environment/`
(gitignored — see `.gitignore` lines 42-44; they are build-time artifacts):

| Variant  | File                 | Contents                                                                                                    |
| -------- | -------------------- | ----------------------------------------------------------------------------------------------------------- |
| standard | `Dockerfile`         | base image by language + git-clone every `[[repos]]` entry into `/workspace/<path>`                         |
| sg_only  | `Dockerfile.sg_only` | ubuntu:22.04, EMPTY workspace, `SOURCEGRAPH_REPOS`/`SOURCEGRAPH_REPO_NAME` env, `/tmp/.sg_only_mode` marker |
| hybrid   | `Dockerfile.hybrid`  | standard clones + Sourcegraph env var                                                                       |

**Trap — run_task.py ALWAYS builds the `standard` variant**, for every mode
including `mcp_only` (`_generate_dockerfile` returns `results["standard"]`
and errors if it is missing). `Dockerfile.sg_only` is generated but unused by
the production runner. This is intentional current design, not a bug:
mcp_only is enforced by prompt preamble plus 0-MCP-call invalidation, not by
an empty workspace. Do not "fix" it without change control (see eb-mcp-modes).

Key generation facts (all in `dockerfile_generator.py`):

- **Base image by language** (`_base_image_for_languages`): go →
  `golang:1.21-bookworm`, python → `python:3.11-bookworm`, java →
  `eclipse-temurin:17-jdk-jammy`, rust → `rust:1.75-bookworm`, js/ts →
  `node:20-bookworm`, c/c++ → `gcc:13-bookworm`, csharp → dotnet sdk 8.0,
  fallback `ubuntu:22.04`.
- **Baked-in setup**: git/curl/jq via apt, Node.js 20 via official tarball
  (unless a `node:` base), `npm install -g @anthropic-ai/claude-code@latest`,
  a non-root `agent` user created and owning `/workspace`, then `USER agent`
  BEFORE the clones — so cloned repos are agent-owned from the start.
- **Clone source**: `--source mirror` (default) clones
  `https://github.com/<ORG>/<mirror>.git --depth 1` using
  `scripts/infra/mirror_naming.py::derive_mirror_name` (single source of
  truth — never hand-derive mirror names; see eb-sourcegraph-mirrors).
  `--source upstream` clones the original URL: `--depth 1 --branch <rev>` for
  tags, full clone + `git checkout <sha>` for SHAs (git's `--branch` does not
  accept commit SHAs).
- Repos with missing `url`/`rev`/`path` are silently skipped in generation
  (but `validate_repo_entry` runs first on every entry).

`scripts/sandbox/sandbox_builder.py`, `build_all.sh`, `measure_all.sh`, and
`health_check.sh` (the marker-file one) belong to the standalone
template-measurement path, NOT the production run path. run_task.py imports
`dockerfile_generator` directly and uses its own inline health check.

## Image tags, container names, and cache collisions

From `run_task()` (run_task.py ~line 1506):

```
image_tag       = eb-<task_id>[-<mode>][-ablate-<variant>]     # no suffix for baseline
container_name  = eb-run-<task_id>[-<mode>][-ablate-<variant>]-<time_ns>
```

Examples: `eb-api-contract-001` (baseline), `eb-api-contract-001-mcp_only`,
`eb-api-contract-001-ablate-etcd`.

Why: concurrent runs of the same task in different modes would otherwise race
on one Docker tag, and the build cache could hand a non-ablated image to an
ablation run. The mode suffix is what makes the repo's "always parallelize
across modes/accounts" convention safe. `--no-build` reuses the existing
image FOR THAT EXACT TAG — a baseline image does not satisfy an mcp_only run.

## Container setup: what lands where

`_setup_container` populates the running container:

| In-container path                                                                | Source                                                                                 | Notes                                                                                       |
| -------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| `/workspace/instruction.md`                                                      | task `instruction.md` + generated output appendix (+ MCP preamble for mcp_only/hybrid) | built by `_build_instruction_text`; appendix mandates `/workspace/agent_output/answer.json` |
| `/workspace/.verifiers/<name>.sh`                                                | task `checks/check_<name>.sh`                                                          | `check_` prefix stripped; `chmod +x` applied                                                |
| `/workspace/test.sh`                                                             | `scripts/sandbox/test_runner.sh`                                                       | the in-container scorer                                                                     |
| `/workspace/.eb_verify/eb_verify/`                                               | `lib/eb_verify/`                                                                       | see docker-cp trap below                                                                    |
| `/workspace/.task/ground_truth.json`                                             | task `ground_truth.json`                                                               | verifiers read it via `TASK_DIR`                                                            |
| `/workspace/.mcp.json`, `/home/agent/.mcp.json`, `/home/agent/.claude/.mcp.json` | written later by `_configure_mcp` (MCP modes only)                                     | see eb-mcp-modes                                                                            |
| `/workspace/agent_output/`                                                       | created by the agent step (`mkdir -p` in the exec command)                             | canonical artifact dir                                                                      |

## The docker-cp directory-semantics trap

`docker cp SRC_DIR CONTAINER:DEST` behaves differently depending on whether
DEST exists:

- DEST **exists**: SRC_DIR is copied INTO it → `DEST/SRC_DIR/...`
- DEST **does not exist**: docker creates DEST and copies SRC_DIR's
  **contents** into it → the package directory itself vanishes.

Incident (beads EnterpriseBench-hktt/pt0n, fixed in commit 16280cf): the
`eb_verify` copy ran without a preceding `mkdir -p /workspace/.eb_verify`, so
the container got `/workspace/.eb_verify/<contents>` with no `eb_verify/`
package dir. `python3 -m eb_verify...` under
`PYTHONPATH=/workspace/.eb_verify` raised `ModuleNotFoundError`, verifiers
scored a silent 0.0, and **5 published refactor-orchestration runs were
contaminated**. The fix is two lines in `_setup_container` (~line 563):

```python
_docker_exec(container_id, ["mkdir", "-p", "/workspace/.eb_verify"])
_docker_cp(str(EB_VERIFY_LIB), f"{container_id}:/workspace/.eb_verify/")
```

**The `mkdir -p` is load-bearing.** It looks redundant; it is not. Never
remove it, and replicate the pattern (mkdir the destination first) any time
you docker-cp a directory whose name must survive.

## chown and readability: the fail-loud gates

docker cp preserves the host UID, which does not match the in-container
`agent` user. History (bead EnterpriseBench-s58f): a chown failure was
silently swallowed → `instruction.md` unreadable by `agent` → the agent never
started → the run recorded `success=True, num_turns=0, score=0.0` — a fake 0
that corrupted the MCP-vs-baseline comparison. Three mechanisms now guard
this:

1. **`_chown_to_agent(container_id, paths)`** — chowns each existing path to
   `agent:agent` as root; missing paths are skipped (some are created later,
   by design); a genuine failure is logged at ERROR level, never swallowed.
   Applied after setup to: `/workspace/instruction.md`, `.verifiers`,
   `.task`, `.eb_verify`, `test.sh`. Deliberately NOT `chown -R /workspace`
   (too slow for kubernetes-sized repos) and deliberately NOT `.mcp.json` /
   `agent_output` at setup time (those are created/chowned by later steps;
   chowning stale leftovers from a reused container was part of the s58f
   design discussion).
2. **`_assert_agent_readable`** — pre-agent gate: `docker exec -u agent test
-r <path>` for `/workspace/instruction.md` (+ `/workspace/.mcp.json` and
   `/home/agent/.mcp.json` in MCP modes), run AFTER a re-chown of those same
   targets. Failure → `phase=agent_preflight_failed`, `status=invalid`,
   `failure_class=infra_perms`. The run is never scored.
3. **`_scan_mcp_config_error`** — post-agent scan of `agent_stderr.log` for
   the audited no-op markers (`Invalid MCP configuration`,
   `instruction.md: Permission denied`, `EACCES` + `.mcp.json`). A hit →
   `status=invalid`, `failure_class=infra_mcp_config`.

If you add any new file the agent must read, add it to BOTH the chown list
and the readability targets. A file the agent cannot read is an invalid run,
not a 0.

## MCP pre-flight hard gate (summary — details in eb-mcp-modes)

For mcp_only/hybrid, `_configure_mcp` must return True before the agent runs:
curl HTTP check on the Sourcegraph MCP endpoint (5 retries), `.mcp.json`
written to three locations via docker cp, then `claude mcp list` handshake (5
retries, must show "Connected"). A False return is a HARD gate:
`phase=mcp_infra_error`, `status=invalid`, `failure_class=infra_mcp_preflight`.
History (bead EnterpriseBench-c7wb, commits 9832487 + daca3cc): before the
gate, a failed pre-flight let a degraded no-MCP agent run be recorded as a
real mcp_only measurement, corrupting the MCP arm.

Additionally, an MCP-mode run where the agent made 0 `mcp__sourcegraph__`
calls gets `tool_usage["mcp_used"] = False` — flagged as not valid MCP
comparison data (but NOT status=invalid; the flag is applied downstream).

## Scoring inside the container (what run_task actually records)

`_run_scoring` executes `bash /workspace/test.sh` (= `test_runner.sh`) with
`WORKSPACE=/workspace TASK_DIR=/workspace/.task
PYTHONPATH=/workspace/.eb_verify` exported. test_runner.sh:

- discovers repos (dirs with `.git`), refuses to run if any is inaccessible;
- runs every `/workspace/.verifiers/*.sh` with a 120s default timeout;
- parses each verifier's stdout as JSON if it starts with `{`; otherwise
  falls back to exit-code semantics (0 → score 1.0, nonzero → 0.0);
- emits `task_score` as a RAW (un-normalized) sum. Weighting semantics
  (`.meta` sidecars, equal-weighting-at-HEAD, the origin/main delta that
  changes this on pull, downstream normalization in `analyze_scores.py`)
  are owned by **eb-checkpoint-scoring §1–§3** — read the stale-on-pull
  warning there before relying on any weighting claim; do not restate the
  mechanics here.

The weighted-and-tested library scorer (`lib/eb_verify/runner.py::
CheckpointRunner`) is NOT on this path — production scoring is run_task.py +
test_runner.sh. PROVISIONAL pending Stephanie: whether the two scorers get
consolidated, the library becomes a CI oracle, or `.meta` weight propagation
lands is an OPEN decision (discovery Q3). Do not canonize either path; see
eb-checkpoint-scoring.

Single-checkpoint debugging: `bash /workspace/test.sh <checkpoint_name>` runs
one verifier and prints its JSON.

## Silent-zero guard inventory

The doctrine (see eb-scoring-integrity-doctrine): a score is valid only if
the pristine verifier ran on real agent output; every infra failure must
surface as an infra error, never a 0.0.

| Guard                               | Trigger                                 | Result                                                                 | Incident                  |
| ----------------------------------- | --------------------------------------- | ---------------------------------------------------------------------- | ------------------------- |
| mkdir-before-docker-cp              | eb_verify copy                          | package dir survives                                                   | hktt/pt0n, commit 16280cf |
| `_chown_to_agent` fail-loud         | chown failure                           | ERROR log, never swallowed                                             | s58f                      |
| `_assert_agent_readable`            | agent can't read instruction/.mcp.json  | `status=invalid`, `infra_perms`                                        | s58f                      |
| MCP pre-flight hard gate            | endpoint/handshake failure              | `status=invalid`, `infra_mcp_preflight`                                | c7wb, 9832487/daca3cc     |
| `_scan_mcp_config_error`            | no-op markers in agent stderr           | `status=invalid`, `infra_mcp_config`                                   | validity audit uu8z       |
| exit-code classification            | 137 / 124                               | `infra_oom` / `infra_timeout`, `phase=agent_infra_error`               | —                         |
| `_apply_llm_judge` no-output branch | llm_curator task, no agent artifact     | `scores["verifier_infra_error"]`, `failure_class=verifier_infra_error` | audit 2026-07-06          |
| 0-MCP-call flag                     | MCP mode, no `mcp__sourcegraph__` calls | `mcp_used=False` (flag only)                                           | —                         |

### Known LIVE gaps on main (2026-07-06 deep-audit, verified still present 2026-07-07)

Do not be surprised by these, and do not fix them ad hoc — they are tracked
(bead EnterpriseBench-apfp) and the accepted direction is a consolidated
`scorer_guard(agent_output, verifier_result) -> Score | InfraError` plus a
`tests/integrity/` adversarial corpus. PROVISIONAL pending Stephanie: that
consolidation is the designated campaign spine (discovery Q2) but is NOT
landed; treat it as open/candidate.

1. **Broken `test.sh` persisted as a legit 0.0** — a crashed verifier is
   recorded as a real score.
2. **Judge failure reverts to un-capped grep scores** — a judge outage
   inflates scores.

Line-number anchors, failure modes, and re-verify commands for both live in
ONE home: **eb-scoring-integrity-doctrine (P4/P5)**. Do not restate them
here — when the scorer_guard campaign fixes them, the doctrine skill is the
only file that must change.

If you touch `_run_scoring` or `_apply_llm_judge`: this is the production
scoring path. Treat the change as HALT-branch-ready — Stephanie's explicit
approval before merge, tests ship in the same commit (PROVISIONAL pending
Stephanie: conservative-gating position, discovery Q5).

## failure_class and status reference

| failure_class                 | Meaning                                   | Scoreable?                    |
| ----------------------------- | ----------------------------------------- | ----------------------------- |
| `infra_disk`                  | disk pre-flight failed                    | no (never ran)                |
| `infra_build`                 | docker build failed                       | no                            |
| `infra_clone`                 | container setup / CLI install failed      | no                            |
| `infra_auth`                  | OAuth token missing/expired (`--account`) | no                            |
| `infra_perms`                 | readability gate failed                   | NO — `status=invalid`, re-run |
| `infra_mcp_preflight`         | MCP hard gate failed                      | NO — `status=invalid`, re-run |
| `infra_mcp_config`            | MCP/EACCES no-op markers post-agent       | NO — `status=invalid`, re-run |
| `infra_oom` / `infra_timeout` | agent exit 137 / 124                      | infra error, re-run channel   |
| `agent_error`                 | agent exited nonzero (other)              | scores still computed         |
| `verifier_infra_error`        | Tier-2 cap could not be applied           | NO — re-run channel           |

`--account N` reads `~/.claude-homes/accountN/.claude/.credentials.json` on
the HOST, validates expiry, and injects `CLAUDE_CODE_OAUTH_TOKEN` via a temp
`--env-file` (not visible in `ps`). Expired token → `infra_auth` with the
remediation command in the error (`scripts/infra/headless_login.py`). With
`--account` and no `--agent`, the default agent command is
`claude --dangerously-skip-permissions --max-turns 50 --verbose
--output-format stream-json -p`. Agent commands must match
`^[\w./@: -]+$` — no quotes, pipes, or shell metacharacters.

## Output layout

`results/runs/<task_id>/<mode>/[rep<N>/]` (or `--output-dir`):

```
results.json        # scores, phase, failure_class, image_tag, timing, config
config.json         # run-config snapshot
task_metrics.json   # timing + tool_usage + status (used by --skip-completed)
agent_stdout.log / agent_stderr.log   # flat, backward-compat
agent/stdout.log / agent/stderr.log   # same content, new layout
agent_trace.jsonl   # Claude Code conversation trace (best-effort copy)
verifier/output.json
```

Always pass `--rep N` for repeated runs — without it, reps overwrite each
other in the mode directory.

## Debugging runbook

```bash
# 1. Keep the container after a failing run
python3 scripts/orchestration/run_task.py <task.toml> --keep-container ...

# 2. Find it (name embeds task id + mode + timestamp)
docker ps -a --filter name=eb-run-

# 3. Inspect the workspace as the agent user
docker exec -u agent -w /workspace <cid> ls -la /workspace
docker exec -u agent <cid> test -r /workspace/instruction.md && echo readable

# 4. Re-run scoring manually (exactly what _run_scoring does)
docker exec -w /workspace <cid> bash -c \
  'export WORKSPACE=/workspace TASK_DIR=/workspace/.task PYTHONPATH=/workspace/.eb_verify; bash /workspace/test.sh'

# 5. One checkpoint only
docker exec -w /workspace <cid> bash -c \
  'export WORKSPACE=/workspace TASK_DIR=/workspace/.task PYTHONPATH=/workspace/.eb_verify; bash /workspace/test.sh error_chain'

# 6. Verify the docker-cp trap didn't recur
docker exec <cid> test -d /workspace/.eb_verify/eb_verify && echo package-dir-ok

# 7. Clean up
docker rm -f <cid>
```

Common symptom table:

| Symptom                                                    | Likely cause                                                                                                  | Check                                                                    |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `ModuleNotFoundError: eb_verify` in verifier output        | docker-cp trap recurred                                                                                       | step 6 above                                                             |
| `success=True, num_turns=0, score=0.0`                     | pre-s58f-style no-op run — the gates should have caught it; treat the run as invalid and investigate the gate | `agent_stderr.log` for `Permission denied` / `Invalid MCP configuration` |
| `task_score: 0.0` with `"error"` key in scores             | broken test.sh persisted as 0.0 (live gap #1)                                                                 | `verifier/output.json` for the `error` field                             |
| Build succeeds for baseline, mcp_only run uses stale image | `--no-build` with wrong tag                                                                                   | `docker images                                                           | grep eb-<task_id>` — the mode suffix must match |
| Health check warnings but run continues                    | by design — health check is not a gate                                                                        | logs: "continuing anyway"                                                |

## Provenance and maintenance

Authored 2026-07-07 against the working tree at
`scripts/orchestration/run_task.py` (2016 lines, 42 historical touches — the
churn hotspot; its size is why silent-fallback bugs slid through review, per
the 2026-07-06 audit). Line numbers are approximate and will drift; anchor on
function names.

Re-verify before trusting drift-prone claims:

```bash
# Flags and defaults
python3 scripts/orchestration/run_task.py --help

# Image-tag scheme (mode/ablation suffixes)
grep -n 'mode_suffix\|ablation_suffix\|image_tag = ' scripts/orchestration/run_task.py

# docker-cp trap fix still present (mkdir before cp)
grep -n -B2 'workspace/.eb_verify/' scripts/orchestration/run_task.py | grep mkdir

# Fail-loud gates still present
grep -n '_assert_agent_readable\|_chown_to_agent\|_scan_mcp_config_error\|RUN_STATUS_INVALID' scripts/orchestration/run_task.py

# Live gaps still unfixed? (if these route to verifier_infra_error now, update this skill)
sed -n '800,820p' scripts/orchestration/run_task.py
grep -n 'except Exception as exc' scripts/orchestration/run_task.py

# Production scorer still equal-weighted (no .meta emitted)
grep -n '\.meta' scripts/sandbox/test_runner.sh scripts/orchestration/run_task.py

# task_score still a raw sum (normalized downstream)
grep -n 'normalized_score' scripts/analyze_scores.py

# Standard Dockerfile still the only variant built by run_task
grep -n 'results.get("standard")' scripts/orchestration/run_task.py

# Incident commits
git log --oneline 16280cf 9832487 daca3cc | head -3
```
