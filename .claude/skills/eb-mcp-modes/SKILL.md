---
name: eb-mcp-modes
description: >
  Tool-access modes in EnterpriseBench: baseline vs mcp_only vs hybrid, how
  Sourcegraph MCP is wired into the sandbox via .mcp.json files, the
  SOURCEGRAPH_ACCESS_TOKEN / .env.local credential path, the MCP pre-flight
  hard gate (never score a degraded MCP run), the 0-MCP-call mcp_used flag,
  and why mcp_only STILL clones repos into /workspace (intentional, not a
  bug). Load this skill when: running or debugging an mcp_only or hybrid
  task; a run fails with infra_mcp_preflight, mcp_infra_error,
  infra_mcp_config, or "MCP pre-flight FAILED"; `claude mcp list` shows
  needs-auth; you see 401/expired-token errors against demo.sourcegraph.com;
  an MCP-mode run recorded 0 MCP tool calls; you are about to compare MCP vs
  baseline scores; or you are tempted to "fix" the fact that mcp_only
  containers contain local source code.
---

# eb-mcp-modes — the tool-access independent variable

Tool access is EnterpriseBench's controlled independent variable. The whole
benchmark exists to measure whether Sourcegraph MCP navigation changes agent
performance, so anything that blurs the line between the arms (a degraded MCP
run scored as a real MCP measurement, an MCP run that never called MCP)
corrupts the experiment, not just one number. This skill covers the three
modes, the MCP plumbing, and the validity gates around it.

All `file:line` references were verified against the repo on 2026-07-07.

## When NOT to use this skill

| You actually want                                                                          | Use instead                     |
| ------------------------------------------------------------------------------------------ | ------------------------------- |
| Provisioning/naming sg-evals mirrors, `sg_indexing_list.json`, `mirrors_indexed` preflight | `eb-sourcegraph-mirrors`        |
| The sandbox lifecycle (Dockerfile build, container setup, docker-cp traps, chown gates)    | `eb-sandbox-execution`          |
| How scores are computed, the two scorers, judge caps                                       | `eb-checkpoint-scoring`         |
| The never-silent-misscore doctrine itself                                                  | `eb-scoring-integrity-doctrine` |
| Running a whole campaign and analyzing results                                             | `eb-run-and-analyze`            |
| chain / event_replay / resume sessions                                                     | `eb-session-types`              |
| First contact with the repo                                                                | `eb-orientation`                |

## 1. The three modes

Defined in `scripts/orchestration/run_task.py:67` and mirrored in
`scripts/run_benchmark.py:78`:

```python
VALID_MODES = ("baseline", "mcp_only", "hybrid")
```

|                                                                               | baseline                           | mcp_only                                                   | hybrid                                                      |
| ----------------------------------------------------------------------------- | ---------------------------------- | ---------------------------------------------------------- | ----------------------------------------------------------- |
| Sourcegraph MCP configured                                                    | no                                 | yes                                                        | yes                                                         |
| MCP preamble prepended to instruction.md                                      | no                                 | `_MCP_ONLY_HEADER` ("Local source files are not present…") | `_HYBRID_HEADER` (MCP for discovery, local for reads/edits) |
| Repos cloned into `/workspace/`                                               | yes                                | **yes (see §3)**                                           | yes                                                         |
| MCP pre-flight hard gate                                                      | n/a                                | yes                                                        | yes                                                         |
| `SOURCEGRAPH_ACCESS_TOKEN` + `NODE_TLS_REJECT_UNAUTHORIZED=0` passed to agent | no                                 | yes                                                        | yes                                                         |
| Docker image tag                                                              | `eb-<task_id>`                     | `eb-<task_id>-mcp_only`                                    | `eb-<task_id>-hybrid`                                       |
| Results dir                                                                   | `results/runs/<task_id>/baseline/` | `.../mcp_only/`                                            | `.../hybrid/`                                               |

Mechanically, mode changes exactly five things in `run_task.py`:

1. **Instruction text** — `_build_instruction_text` (`run_task.py:343`)
   prepends the mode preamble from
   `agents/harnesses/claude/mcp/sourcegraph.py::build_system_prompt`
   (returns `""` for baseline, `sourcegraph.py:208`), plus the task's
   optional `instruction_mcp.md` if present (5 active tasks have one as of
   2026-07-07). The combined text is docker-cp'd to
   `/workspace/instruction.md` (`run_task.py:504-525`).
2. **MCP config** — `_configure_mcp` (`run_task.py:1146`) runs only for
   mcp_only/hybrid.
3. **Agent env** — `NODE_TLS_REJECT_UNAUTHORIZED=0` and
   `SOURCEGRAPH_ACCESS_TOKEN` are injected for MCP modes
   (`run_task.py:1636-1646`).
4. **Image tag suffix** (`run_task.py:1506-1510`) — prevents Docker build
   cache collisions when running the same task in two modes in parallel.
5. **Output partition** (`run_task.py:1518-1527`) —
   `results/runs/<task_id>/<mode>/rep<N>/`.

The preamble also injects per-repo Sourcegraph scoping filters
(`repo:^github.com/sg-evals/...$`) derived by
`scripts/infra/mirror_naming.py::derive_mirror_name`
(`sourcegraph.py:180-184`) — the single source of truth for mirror names
(details: `eb-sourcegraph-mirrors`).

## 2. Running each mode (copy-paste)

Single task (worker script — the caller must parallelize, per CLAUDE.md):

```bash
# baseline
python3 scripts/orchestration/run_task.py benchmarks/<suite>/<task>/task.toml \
  --account 1 --rep 1 --mode baseline

# mcp_only (requires .env.local token, see §4)
python3 scripts/orchestration/run_task.py benchmarks/<suite>/<task>/task.toml \
  --account 2 --rep 1 --mode mcp_only

# hybrid
python3 scripts/orchestration/run_task.py benchmarks/<suite>/<task>/task.toml \
  --account 3 --rep 1 --mode hybrid
```

Batch dispatcher (`scripts/run_benchmark.py:504-517`): `--mode <m>` for one
mode, or `--modes baseline,mcp_only,hybrid` to run every task in each mode
(overrides `--mode`; each mode writes to its own
`results/runs/<task_id>/<mode>/` subdirectory). Chain sessions accept the
same `--mode` flag and propagate it to every session in the chain
(`scripts/orchestration/chain_runner.py:283-284,181-183`).

With `--account N`, the default agent command is
`claude --dangerously-skip-permissions --max-turns 50 --verbose
--output-format stream-json -p` (`run_task.py:180`) and, for MCP modes,
`--mcp-config /home/agent/.mcp.json` is appended automatically
(`run_task.py:1662-1668`). Caveat: that auto-append happens only inside the
`--account` branch — if you pass a custom `--agent` command without
`--account` in an MCP mode, the agent relies on auto-discovery of
`/workspace/.mcp.json` alone.

## 3. mcp_only still clones repos locally — intentional, do not "fix"

The single most misread design in the repo. Reality, verified 2026-07-07:

- `run_task.py::_generate_dockerfile` (`run_task.py:207-221`) always selects
  the **`standard`** Dockerfile variant — local clones of every task repo
  into `/workspace/<path>/` — **regardless of mode**.
- `scripts/sandbox/dockerfile_generator.py::generate_for_task`
  (`dockerfile_generator.py:307-350`) does generate three variants per task
  (`Dockerfile`, `Dockerfile.sg_only` with an empty workspace and a
  `/tmp/.sg_only_mode` marker, `Dockerfile.hybrid`), but **run_task.py never
  builds `Dockerfile.sg_only` or `Dockerfile.hybrid`**. They are written to
  the task's `environment/` dir and unused by the production path.
- Meanwhile the mcp_only preamble (`sourcegraph.py:59-62`) tells the agent:
  "Local source files are not present in /workspace. You MUST use
  Sourcegraph MCP tools for all code access." — which is **false at the
  filesystem level**. mcp_only is enforced by **prompt**, and audited after
  the fact via the MCP-call count (§6), not by an empty workspace.

Consequences:

- Do not file "mcp_only containers contain source code" as a bug, and do not
  swap the build to `Dockerfile.sg_only` as a drive-by. Changing the
  enforcement mechanism changes what the MCP arm measures — it invalidates
  comparability with every existing mcp_only run. Treat it as a
  scoring-path-adjacent change (see §7).
- An mcp_only agent CAN cheat by reading `/workspace` directly. The
  detection signal is `mcp_tool_calls` in `tool_usage` (§6) plus the agent
  trace (`agent_trace.jsonl`); there is no hard filesystem barrier as of
  2026-07-07.
- Verifiers looking for `/tmp/.sg_only_mode` will never find it in real
  runs, because the sg_only image is never built.

## 4. Token and endpoint configuration

**Token source.** `run_task.py:31-43` auto-loads `<repo-root>/.env.local` at
import time, but only if `SOURCEGRAPH_ACCESS_TOKEN` is not already in the
environment. It parses `KEY=VALUE` and `export KEY=VALUE` lines, strips
quotes, and uses `os.environ.setdefault` (existing env always wins).
`.env.local` is gitignored; the relevant keys present in the working copy
(names only, 2026-07-07): `SOURCEGRAPH_ACCESS_TOKEN`, `SOURCEGRAPH_MCP_URL`,
`SOURCEGRAPH_URL`, `SOURCEGRAPH_ENDPOINT`, `SRC_ENDPOINT`. Only the first
two are read by `run_task.py`.

**Endpoint.** `run_task.py:69-76`:

- Default: `https://demo.sourcegraph.com/.api/mcp/all` (volatile —
  demo-instance tokens expire; a 401 here is the classic failure).
- `SOURCEGRAPH_MCP_URL` overrides it; a missing `/all` suffix is appended
  automatically (`/all` exposes 13 tools vs 8 on the base endpoint, per the
  in-code comment).

**Missing token behavior.** `_configure_mcp` only **warns** when the token
is empty (`run_task.py:1166-1168`) and then skips the curl check (it is
inside `if sg_token:`), so an empty token falls through to the
`claude mcp list` handshake, which then fails the gate. You still get a hard
stop, but the error is less specific — check the token first when triaging.

**TLS.** All MCP-mode agent and pre-flight execs set
`NODE_TLS_REJECT_UNAUTHORIZED=0` and curl uses `-k` (`run_task.py:1075,
1115`) — the demo endpoint's TLS is not verified. Scope: sandbox-internal.

## 5. How MCP is wired: .mcp.json files, never `claude mcp add`

`_configure_mcp` (`run_task.py:1146-1300`), for mcp_only/hybrid only:

1. **HTTP pre-check** — `_verify_mcp_endpoint` (`run_task.py:1087`) curls
   the endpoint from inside the container with
   `Authorization: token <sg_token>`, 5 attempts with exponential backoff;
   HTTP 200 or 405 counts as reachable+authenticated (405 = GET on a
   POST-only MCP endpoint). Failure → return False → hard gate (§6).
2. **Config files** — writes the same JSON to three container paths via
   `docker cp` (shell-escaping-safe), chowned to `agent`:
   - `/workspace/.mcp.json` (project-level, Claude Code auto-discovers)
   - `/home/agent/.claude/.mcp.json` (user-level fallback)
   - `/home/agent/.mcp.json` (target of the explicit `--mcp-config` flag)

   Shape:

   ```json
   {
     "mcpServers": {
       "sourcegraph": {
         "type": "http",
         "url": "https://demo.sourcegraph.com/.api/mcp/all",
         "headers": { "Authorization": "token <SOURCEGRAPH_ACCESS_TOKEN>" }
       }
     }
   }
   ```

3. **Handshake verification** — `claude mcp list` inside the container, up
   to 5 attempts with backoff, looking for `sourcegraph` + `Connected`
   (`run_task.py:1250-1296`). `needs-auth` is retried as a timing issue.

`claude mcp add` is deliberately NOT used — the CLI command had race
conditions causing intermittent needs-auth (`run_task.py:75-76,1155`).
Keep it that way.

Known flakiness (validity audit
`docs/qa/locked_runset_mcp_token_validity_audit_966x.md`, 2026-06-25): the
`claude mcp list` handshake is the flaky half — 34 audited runs recorded a
failed handshake while having 15–91 real authenticated MCP calls. The curl
check is the reliable token-validity signal. The gate is fail-safe (false
positives waste re-runs, never corrupt scores); weighting the gate toward
the curl result is a recorded candidate refinement, **not landed** as of
2026-07-07.

## 6. The validity gates

### 6a. MCP pre-flight is a HARD gate (incident c7wb)

History: MCP pre-flight failure once let the agent proceed "degraded" — no
working MCP — and the result was recorded as a real mcp_only measurement,
corrupting the MCP-vs-baseline comparison (bead EnterpriseBench-c7wb).
The fix (`run_task.py:1587-1615`): if `_configure_mcp` returns False, the
run stops before the agent phase with:

- `phase = "mcp_infra_error"`, `success = False`
- `failure_class = "infra_mcp_preflight"`
- `result.status = RUN_STATUS_INVALID` (`"invalid"`, `run_task.py:104`)

and is routed to the infra-error re-run channel. Regression tests:
`tests/test_mcp_preflight_gate.py`, `tests/test_mcp_config.py`.

**Reading a gated run from disk:** the in-process `status` field is NOT
persisted — the `results.json` / `task_metrics.json` payloads
(`run_task.py:992-1015,1034-1042`) carry `success`, `phase`, and
`failure_class` but no `status` key (verified 2026-07-07). Identify invalid
runs by `"success": false` + `"failure_class": "infra_mcp_preflight"` (or
the other infra classes below), never by grepping for `"status": "invalid"`.
The re-run mechanics rely on this: `run_benchmark.py::is_task_completed`
(`run_benchmark.py:195-228`) skips a task only when `"success": true`, so
`--skip-completed` automatically retries gated runs.

Two more pre-agent invalidity gates share the channel (both from bead
EnterpriseBench-s58f; details in `eb-sandbox-execution`):

| Gate                                                                   | failure_class      | Where                                                     |
| ---------------------------------------------------------------------- | ------------------ | --------------------------------------------------------- |
| Agent user cannot read `instruction.md` / `.mcp.json` files            | `infra_perms`      | `run_task.py:1685-1704`                                   |
| Agent stderr shows "Invalid MCP configuration" / EACCES on `.mcp.json` | `infra_mcp_config` | `_scan_mcp_config_error`, `run_task.py:470-487,1734-1741` |

### 6b. 0-MCP-call flagging (post-run)

After the agent runs, `_extract_tool_usage` counts MCP calls by counting
`mcp__sourcegraph__` occurrences in the agent stdout log
(`run_task.py:1387`). Then (`run_task.py:1745-1755`):

- MCP mode with `mcp_tool_calls == 0` → warning logged and
  `tool_usage["mcp_used"] = false` in results.json.
- MCP mode with calls > 0 → `tool_usage["mcp_used"] = true`.

Precision matters here: **a 0-MCP-call run is flagged, not auto-invalidated**
— it is NOT given `RUN_STATUS_INVALID` and still gets scored (verified
2026-07-07). As of 2026-07-07 no analysis script filters on
`mcp_used`/`mcp_tool_calls` automatically (`scripts/analyze_scores.py` has
no such filter); exclusion happens in the human/audit layer — the 966x
validity audit used per-run `mcp_tool_calls` and `agent_trace.jsonl`
`tool_result` entries as the decisive criterion for whether an mcp_only run
was a real MCP measurement. When you build any MCP-vs-baseline comparison,
you must check `mcp_used` yourself; do not assume the pipeline did.
(The 966x audit references a `docs/qa/locked_runset_dispositions.csv` with
per-run call counts; that file is not present in the working copy as of
2026-07-07 — treat the audit markdown as the surviving record.)

## 7. Change discipline for this surface

The mode plumbing IS the experiment. PROVISIONAL pending Stephanie (Q5
provisional answer, recorded 2026-07-07): treat changes to any of the
following AS IF HALT-branch-ready — branch + tests, stop at branch-ready,
Stephanie approves before merge — same as production-scoring-path changes:

- the pre-flight gate logic or its failure routing (`_configure_mcp`, the
  hard-gate branch in `run_task`)
- the mode preambles in `agents/harnesses/claude/mcp/sourcegraph.py`
  (prompt text is the mcp_only enforcement mechanism)
- the Dockerfile variant selection (§3)
- the `mcp_tool_calls` / `mcp_used` accounting

PROVISIONAL pending Stephanie (Q4): never state a positive MCP lift as fact
in any output of this skill's procedures. The honest current state
(2026-07-07) is the locked N=105 parity headline (mean −0.093 / median 0.0 /
no MCP win), audited clean of token-expiry contamination by 966x. Whether
the dose-response study changes that is open; prove whichever sign the data
has.

`agents/harnesses/claude/mcp/preamble_variants.py` (Experiment P1 tool-
selection variants) has no production consumers as of 2026-07-07 —
experimental material, not part of the run path.

## 8. Failure triage

| Symptom                                            | Likely cause                                                                | First command                                                                                          |
| -------------------------------------------------- | --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `failure_class: infra_mcp_preflight`               | Expired/rejected SG token, endpoint down, or `claude mcp list` timing flake | curl check in §10; if token OK, re-run (gate is fail-safe)                                             |
| `claude mcp list` shows `needs-auth`               | Auth header timing on HTTP transport; retried 5x automatically              | Re-run; persistent → token expired                                                                     |
| 401 from demo.sourcegraph.com                      | Demo-instance token expired (recurring)                                     | Refresh token in `.env.local`                                                                          |
| `mcp_used: false` on an MCP run                    | Agent solved from local clones (see §3) or MCP silently unusable            | Inspect `agent_trace.jsonl` for `mcp__sourcegraph__` tool_use entries                                  |
| `failure_class: infra_mcp_config`                  | `.mcp.json` unreadable/invalid inside container                             | `eb-sandbox-execution` (chown/readability gates)                                                       |
| MCP searches return nothing                        | Wrong mirror scoping / mirror not indexed                                   | `eb-sourcegraph-mirrors` (`mirrors_indexed` preflight warns by design — `_indexed` is hardcoded False) |
| Docker build cache serves wrong image across modes | Missing mode suffix (only if you bypassed run_task)                         | Use `run_task.py`; tags are auto-suffixed                                                              |

## 9. Pre-run checklist for an MCP arm

- [ ] `.env.local` exists at repo root with a current `SOURCEGRAPH_ACCESS_TOKEN`
- [ ] Token actually works (§10 curl one-liner) — don't burn a build to find out
- [ ] Task's mirrors are indexed (see `eb-sourcegraph-mirrors`)
- [ ] `--mode` set on run_task.py / run_benchmark.py (default is baseline — forgetting it silently runs the wrong arm)
- [ ] `--rep N` set if this is a repetition (prevents overwriting)
- [ ] Different `--account` per parallel task (CLAUDE.md: always parallelize across accounts 1-5)
- [ ] After the run: check `tool_usage.mcp_used` in results.json before counting it as MCP data

## Provenance and maintenance

Authored 2026-07-07 (retiring-fellow campaign) against the working tree at
that date; `main` is squash-merged, so line numbers drift — re-verify before
trusting them:

```bash
# Modes still exactly three, in both entry points
grep -n "VALID_MODES" scripts/orchestration/run_task.py scripts/run_benchmark.py

# .env.local auto-load still present and setdefault-based
sed -n '31,43p' scripts/orchestration/run_task.py

# Default endpoint / /all normalization
sed -n '69,76p' scripts/orchestration/run_task.py

# Hard gate still routes preflight failure to infra_mcp_preflight, pre-agent
grep -n "infra_mcp_preflight\|RUN_STATUS_INVALID" scripts/orchestration/run_task.py

# results.json still omits the status field (invalid runs detected via failure_class)
grep -n '"status"' scripts/orchestration/run_task.py || echo "status not persisted (expected)"

# mcp_only still builds the standard (cloning) Dockerfile
grep -n 'results.get("standard")' scripts/orchestration/run_task.py

# sg_only/hybrid Dockerfiles still generated-but-unused by run_task
grep -rn "sg_only\|hybrid" scripts/orchestration/run_task.py | grep -i dockerfile

# 0-MCP-call flag is still flag-only (no analysis-side auto-exclusion)
grep -rln "mcp_used" scripts/ | grep -v pycache

# MCP call counting method unchanged
grep -n "mcp__sourcegraph__" scripts/orchestration/run_task.py

# Preflight gate tests still present and passing (needs pip install -e lib/)
python3 -m pytest tests/test_mcp_preflight_gate.py tests/test_mcp_config.py -q

# Token key names in .env.local (never print values)
grep -oE '^(export )?[A-Za-z_]+=' .env.local

# Live token check (safe, read-only; expect 200 or 405)
source .env.local && curl -sk -o /dev/null -w '%{http_code}\n' \
  -H "Authorization: token $SOURCEGRAPH_ACCESS_TOKEN" \
  "${SOURCEGRAPH_MCP_URL:-https://demo.sourcegraph.com/.api/mcp}/all"
```

Volatile facts to re-check on any drift: the demo.sourcegraph.com default
endpoint and its token expiry cadence; the 5-tasks-with-instruction_mcp.md
count (`find benchmarks -name instruction_mcp.md -not -path "*_archived*"`);
the not-landed status of the curl-weighted gate refinement; both
PROVISIONAL positions in §7.
