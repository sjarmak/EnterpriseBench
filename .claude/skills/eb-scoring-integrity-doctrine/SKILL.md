---
name: eb-scoring-integrity-doctrine
description: >
  THE non-negotiable rule of EnterpriseBench scoring and the catalog of ways it
  has been violated. Load this BEFORE touching any scoring code
  (scripts/orchestration/run_task.py scoring/judge functions,
  scripts/sandbox/test_runner.sh, lib/eb_verify/ validators or runner), before
  reviewing a PR that changes how scores are produced or recorded, before
  trusting or aggregating numbers from results/runs/, when you see a suspicious
  0.0 score, a run recorded success=True with zero turns, an inflated grep
  score, ModuleNotFoundError inside a verifier, or when deciding whether a
  failed run should be scored or re-run. Also load it when someone proposes
  "just return 0.0 on error" or "skip the judge if it fails" — this skill
  explains why that is the project's single most-repeated bug class.
---

# EnterpriseBench Scoring-Integrity Doctrine

Date-stamped 2026-07-07. All file:line references verified against the working
tree at `main` HEAD `7cfb8b0`. Line numbers drift; function names are the
stable anchors. Re-verification commands are at the bottom.

## The invariant

> **A score is valid only if the pristine verifier ran on real agent output.
> Any infrastructure, verifier, or judge failure must surface as
> `verifier_infra_error` (or another `failure_class` on the infra re-run
> channel) — never as a `0.0` and never as an inflated grep score.**

This is the project's one non-negotiable. The benchmark's central deliverable,
in its own words, is "a verification pipeline that survives a skeptic". A
skeptic attacks in exactly two directions, and the invariant closes both:

| Direction                           | Violation                                                                            | What it corrupts                                                            |
| ----------------------------------- | ------------------------------------------------------------------------------------ | --------------------------------------------------------------------------- |
| **Under-credit** (false zero)       | Broken infra scored as `0.0`                                                         | Deflates the affected arm; contaminated published headline numbers (see P1) |
| **Over-credit** (forgery/inflation) | Agent-controlled input trusted by the scorer, or a failed judge cap silently dropped | Inflates scores; lets an agent-under-test grade itself (see P4, P7, P8)     |

The 2026-07-06 deep audit's conclusion, after two years of point patches:
this is **not N unrelated bugs — it is one missing invariant enforced
inconsistently by hand in ~6 places** (`_run_scoring`, `_apply_llm_judge`,
`code_patch.validate`, the docker-cp copy path, `test_runner.sh`, the library
runner), and each site got it subtly wrong in a different way.

### Definitions (jargon, defined once)

| Term                       | Meaning                                                                                                                                                                                                                                                                                                        |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Pristine verifier**      | The `test.sh` / `.verifiers/*.sh` / `ground_truth.json` exactly as copied from the host repo — not whatever is in the container at scoring time. The workspace is chowned to the agent user before its session, so anything in `/workspace` at scoring time is agent-controlled unless re-copied/verified.     |
| **Real agent output**      | An artifact the agent actually produced this run (canonically `/workspace/agent_output/answer.json`). Scoring an empty container, a never-started agent, or a stale artifact is not a measurement.                                                                                                             |
| **Tier 1 / grep score**    | Deterministic bash checkpoint verifiers run by `test.sh`; each prints `{"score": 0-1}`.                                                                                                                                                                                                                        |
| **Tier 2 / judge cap**     | LLM judge over the agent artifact vs `expected_solution.json`; final checkpoint score is `min(grep, judge)` — the judge is a _ceiling_ on inflated grep matches, never a bonus. (`run_task.py::_apply_llm_judge`, `min(grep_score, judge_score)`.)                                                             |
| **`verifier_infra_error`** | The tag meaning "the scorer could not validly run; this is NOT a measurement". Set inside the `scores` dict and mirrored to `result.failure_class` / `result.phase`.                                                                                                                                           |
| **`failure_class`**        | Machine-readable failure taxonomy persisted in `results.json` and `task_metrics.json`. Values in `run_task.py` today: `infra_disk`, `infra_build`, `infra_clone`, `infra_mcp_preflight`, `infra_auth`, `infra_perms`, `infra_oom`, `infra_timeout`, `infra_mcp_config`, `agent_error`, `verifier_infra_error`. |
| **Re-run channel**         | A run tagged with an infra `failure_class` keeps `success=False`, so `run_benchmark.py --skip-completed` (which skips only `"success": true`) will re-run it. That is the whole recovery mechanism — no separate queue.                                                                                        |
| **Silent misscore**        | Any code path that converts an infra/verifier/judge failure into a numeric score. The dominant historical bug class in this repo.                                                                                                                                                                              |
| **`RUN_STATUS_INVALID`**   | In-process marker (`result.status = "invalid"`) set at the MCP pre-flight gate, the readability gate, and the MCP-config scan. **Not persisted**: `_save_results` writes no `status` key. On disk you must infer invalidity from `failure_class`/`phase`/`success`.                                            |

## When NOT to use this skill

| You actually want                                                                                                       | Use instead                    |
| ----------------------------------------------------------------------------------------------------------------------- | ------------------------------ |
| How checkpoints become a task score, the two-scorer (library vs production) split, weights, `min(grep,judge)` mechanics | `eb-checkpoint-scoring`        |
| The `lib/eb_verify/` plugin architecture, adding/altering a validator, groundedness internals                           | `eb-verification-library`      |
| Container lifecycle, docker build/exec/cp mechanics, running one task                                                   | `eb-sandbox-execution`         |
| Running campaigns, `results/` layout, `make analyze` pipeline, promoting runs                                           | `eb-run-and-analyze`           |
| Who must approve a scoring-path change and how it is dispatched                                                         | `eb-git-and-dispatch-workflow` |
| The scorer_guard consolidation campaign itself (phases, gates, commands)                                                | `eb-scorer-guard-campaign`     |
| First map of the whole project                                                                                          | `eb-orientation`               |

Use **this** skill as the checklist and precedent database: it tells you what
must never happen, shows each way it _did_ happen, and gives you the audit
commands to prove your change doesn't add pattern N+1.

## How a score travels (60-second version)

```
run_task.py: build image → clone repos → _setup_container (copies instruction.md,
  .verifiers/, test.sh, .eb_verify/, ground_truth.json; chowns to agent)
→ gates: MCP pre-flight (hard), _assert_agent_readable (hard)
→ agent runs headless in container
→ _run_scoring: bash /workspace/test.sh  → JSON on stdout (Tier 1)
→ _apply_llm_judge (only if task declares llm_curator): min(grep, judge) per checkpoint
→ _save_results: results.json {success, phase, failure_class, scores, …}
→ scripts/analyze_scores.py (make analyze) ingests every results.json it finds
```

Every arrow is a trust boundary, and every violation pattern below lives on
one of them.

## Violation-pattern catalog

Each pattern: the incident, the mechanism, current status, and the rule it
teaches. Status is as of 2026-07-07 at local `main` HEAD `7cfb8b0`. "On a
branch, not on main" means the fix exists but production scoring does not have
it — treat those branches as **parked, not dead**: check the bead store and
branch state before re-implementing or re-landing.

### P1 — Environment-loss silent zero (the docker-cp incident)

**Incident** (beads `hktt`, `pt0n`, `s4a2`; fix commit `16280cf`, on main):
`docker cp` of a directory to a **non-existent** destination copies the
directory's _contents_, not the directory. The `eb_verify` package dir was
dropped, so check scripts running `python3 -m eb_verify.plugins...` under
`PYTHONPATH=/workspace/.eb_verify` died with `ModuleNotFoundError` — and the
verifier fallback scored it a silent `0.0` with no infra flag. All 33 check
scripts invoking that plugin were affected on unpatched main.

**Blast radius** (audit commits `78cfcd2`, `15b50c2`): 27 total silent zeros
found by fingerprint rescan — 16 live cells feeding the `old_locked` headline
across 8 of 11 refactor-orchestration tasks, 5 of 6 baseline-arm cells in one
rerun campaign, plus one contaminated cell that _won the keep-highest dedup_
(see P10) and was what `results/score_analysis.json` — the file `paper.md`
cites — actually published. Some artifacts weren't preserved, making offline
re-score impossible; those cells required full re-runs.

**Fix**: `mkdir -p /workspace/.eb_verify` **before** the `docker cp`
(`run_task.py::_setup_container`, comment block explains the semantics). The
`mkdir` is load-bearing, not redundant — do not "clean it up".

**Rule**: a verifier that cannot import its own tooling has not run. Exit-1 +
`ModuleNotFoundError` in verifier stderr is an infra failure, not a 0.0.

### P2 — Agent never started, recorded as a real run

**Incident** (bead `s58f`): a silently masked `chown` failure left
`instruction.md` unreadable by the agent user. The agent failed to start; the
run was recorded as `success=True, num_turns=0, score=0.0` — a fake
measurement that looks like "agent tried and failed".

**Fix** (on main): two fail-loud gates in `run_task.py`:

- `_assert_agent_readable` — pre-agent `test -r` as the agent user on
  `instruction.md` + `.mcp.json` paths; failure → `failure_class=infra_perms`,
  `phase=agent_preflight_failed`, `status=invalid`, run saved and returned
  **before** the agent phase.
- `_scan_mcp_config_error` — post-agent scan of `agent_stderr.log` for
  `Invalid MCP configuration` / `instruction.md: Permission denied` /
  `EACCES`+`.mcp.json`; hit → `failure_class=infra_mcp_config`,
  `phase=agent_infra_error`.

**Rule**: "the agent produced nothing" and "the agent never got to start" must
be distinguishable in the record. Zero turns + a permission error is the
second one.

### P3 — Degraded arm recorded as a real measurement (MCP pre-flight)

**Incident** (bead `c7wb`; commits `9832487`, `daca3cc`, both on main):
run_task used to log "agent will run but MCP may not work" and proceed when
the Sourcegraph MCP pre-flight failed (unreachable endpoint, expired/rejected
token → 401). The agent ran with no working MCP and the result was recorded as
a real `mcp_only`/`hybrid` measurement — corrupting the MCP-vs-baseline
comparison arm.

**Fix**: hard gate — pre-flight failure routes to
`failure_class=infra_mcp_preflight`, `status=invalid`, `success=False`, return
before the agent runs. Baseline mode is unaffected (no MCP to gate).

**Embedded second lesson** (`daca3cc`): the _first_ hard-gate commit
(`9832487`) referenced symbols that never existed (`mcp_handshake_ok` read but
never assigned, `RUN_STATUS_INVALID` undefined, no `status` field) — every
mcp_only/hybrid run crashed with `NameError` at pre-flight until the follow-up
fixed it. **Integrity gates are scoring-path code: they ship with tests, same
commit.**

**Rule**: a measurement arm whose defining tool was unavailable is not a data
point in that arm. Gate hard; never "proceed degraded".

### P4 — Judge failure silently drops the Tier-2 cap (inflation)

The Tier-2 judge exists to _cap_ grep-pattern over-matching:
`final = min(grep, judge)`. Any path that skips the cap on failure records the
un-capped grep score as if it were the capped measurement — silent inflation.

Three sub-cases in `run_task.py::_apply_llm_judge`, split by status:

| Sub-case                                                                       | Behavior at HEAD `7cfb8b0`                                                                                                                  | Status                                                                                                                                               |
| ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| Task declares `expected_solution` but **no agent artifact found** in container | Tags `scores["verifier_infra_error"] = {reason: "no_agent_output", stage: "llm_judge", …}`; caller sets `failure_class`/`phase` accordingly | **Fixed on main** (bead `hmcp`, audit-2026-06-22 findings #1–2; regression tests in `tests/test_llm_judge_artifact_soundness.py`, 19 tests, passing) |
| **Judge init fails** (import error, judge construction)                        | `logger.warning(...); return scores` — un-capped grep scores flow through as the final measurement                                          | **LIVE violation** (2026-07-06 audit finding #3)                                                                                                     |
| **Per-checkpoint judge call raises**                                           | `logger.warning(...); continue` — that checkpoint keeps its raw grep score                                                                  | **LIVE violation** (same finding)                                                                                                                    |

Artifact discovery is metadata-derived (`_derive_artifact_candidates`:
canonical `agent_output/answer.json` + `/workspace/...` paths named in the
task's `instruction.md`) — it was previously a hardcoded per-task path list,
which is how the no-artifact hole opened.

**Rule**: judge unavailable ⇒ the cap cannot be applied ⇒ the score cannot be
finalized ⇒ `verifier_infra_error`, re-run later. Never fall back to un-capped
grep. If you touch `_apply_llm_judge`, extend the existing tagging pattern to
the two live sub-cases rather than adding a fourth hand-rolled guard.

### P5 — Broken verifier persisted as a legit 0.0

**LIVE violation** (2026-07-06 audit finding #2). `run_task.py::_run_scoring`:
if `test.sh` produces empty stdout or non-JSON stdout, it returns
`{"task_score": 0.0, "all_passed": False, "error": ...}`. The caller inspects
`scores` for `verifier_infra_error` **only after the LLM-judge phase and only
for `llm_curator` tasks** — a broken `test.sh` on a deterministic task sails
through to `phase="complete"`, `success=True`.

**Compounding trap**: because `success=True`,
`run_benchmark.py --skip-completed` will _never re-run it_. The broken-verifier
0.0 is permanent until a human notices. (Contrast with P2/P3, where
`success=False` puts the run back in the re-run channel.)

**Detection**: `scores.error` present alongside `success: true` in
`results.json`. Sweep command in the runbook below (current tree: 0 hits
across 491 results.json files under `results/runs/` — clean today, keep it
that way).

**Rule**: "the verifier printed garbage" is a verifier infra failure. If you
are fixing this, route it through the same `verifier_infra_error` tagging that
`_apply_llm_judge` uses, and make the check mode-independent.

### P6 — Validator collapses git errors into "no changes"

**LIVE violation** (2026-07-06 audit finding #4).
`lib/eb_verify/plugins/code_patch.py`: `_get_diff_stat` catches
`(subprocess.TimeoutExpired, Exception)` and returns `None`; `_get_diff_lines`
likewise returns `0`. `CodePatchValidator.validate` treats `None` as "repo has
no changes" and, if every repo collapses this way, returns
`valid=False, "No code changes detected in any repo under workspace"` — a
false zero manufactured from a git timeout, a corrupt repo, or any raised
exception. Note also the subprocess calls don't check `returncode`: a git
error printing to stderr yields empty stdout → same false "no changes".

**Rule**: inside a validator, "the measuring instrument failed" and "the
measurement is zero" must be different return values. A bare
`except Exception: return None/0` in scoring code is pattern P6 — flag it in
review regardless of what the ticket is about.

### P7 — Agent forges its own score (writable grading files)

**Incident** (bead `7jpm`, two rejection rounds): everything under
`/workspace` — including `test.sh`, `.verifiers/*.sh`, `.verifiers/*.meta`,
`.task/ground_truth.json` — was chowned `agent:agent` before the agent
session, and `_run_scoring` later trusted whatever `test.sh` printed via a
bare `json.loads()`. An agent-under-test could overwrite the verifiers or
`test.sh` and print itself a perfect score.

**Fix — PARKED on branch `fix/eb-7jpm-grading-integrity`, NOT on main**
(commits `f9e3fd1`, `e93bb47`):

- `_copy_grading_files()`: rm -rf + re-copy grading files fresh from host at
  setup **and again immediately before scoring**; grading files owned
  `root:root`, `chmod go-w`.
- `_kill_agent_processes()`: `pkill -9 -u agent` before every refresh (a
  backgrounded writer can outlive its docker-exec session).
- sha256 checksums of grading files at setup, cross-validated before scoring.
- Second round (`e93bb47`): locking individual files is bypassable while
  `/workspace` itself is agent-owned — unlink/rename is gated by the _parent
  directory's_ permissions, so the agent could `mv .verifiers .verifiers.bak
&& mkdir .verifiers`. `_lock_workspace_root()` chowns `/workspace` to
  `root:agent` + sticky bit.

**Consequence for you today**: on main, the "pristine verifier" half of the
invariant is **not mechanically enforced** — scoring trusts the agent-writable
tree. Do not cite main's scores as adversary-proof, and do not re-implement
this from scratch: the parked branch already had two design iterations. Check
its bead thread first.

**Rule**: after the agent has run, nothing in the container is trusted until
re-copied or checksum-verified against the host.

### P8 — Injection through the scoring pipe

Two incidents, one lesson:

- **Python triple-quote injection** (bead `0rv.23`, fixed on main): 37
  file-extraction check scripts shell-interpolated agent-controlled JSON into
  a Python triple-quoted literal (`'''$AGENT_FILES'''`). An agent writing
  `'''` inside a path in `answer.json` could execute arbitrary Python under
  the runner uid. Fixed via a single-process safe template
  (`os.environ['ANSWER_FILE']`); locked by
  `tests/security/test_check_scripts_injection.py`, which enforces the safe
  template by pattern, pins the two legitimately different scripts by sha256,
  and fires adversarial payloads (injection, `sys.exit` bypass, path-spam
  substring cheating).
- **awk/JSON injection in `test_runner.sh`** (bead `wbsq`, commit `8a8236f` —
  **on `origin/main`, not yet in this checkout at `7cfb8b0`**): repo
  basenames, checkpoint names, and `.meta` weight/timeout values were
  interpolated raw into hand-rolled JSON and into an awk arithmetic string —
  including a **verified end-to-end RCE via awk's `system()`** from a crafted
  `.meta` weight. Fix escapes via `json_escape()` and validates weight/timeout
  as plain numbers.

**Rule**: `test.sh` stdout crosses a trust boundary into `_run_scoring`'s
`json.loads()`. Anything agent-influenceable that gets interpolated into that
JSON (or into awk/sed/shell) must be escaped or numerically validated. When
authoring check scripts, never interpolate agent content into code.

### P9 — Unenforced gate the agent is told about (grounded citations)

**Incident** (beads `pakh`/`dec-f5g`/`5eq9`; 2026-07-06 audit finding #1,
HIGH): the grounded-citation gate (verbatim-evidence-span groundedness for
answer citations) lives only on branch `fix/eb-5eq9-preserve-branch-triage`.
At HEAD, `_apply_grounded_citations_gate` does not exist in `run_task.py`
(verified: 0 grep hits), yet `_build_instruction_text` **tells the agent**
citations must be grounded when the task sets
`ground_truth.require_grounded_citations`. Production scoring performs zero
groundedness enforcement.

**Rule**: an integrity gate that is announced but not enforced is worse than
absent — it manufactures a false defensibility claim. Never document or
promise a gate in instructions/README until it runs in the production scoring
path.

### P10 — Aggregation masks contamination (keep-highest dedup)

**LIVE hazard**. `scripts/analyze_scores.py::load_all_results` deduplicates
`(task_id, mode)` by **keeping the highest normalized score**, and
`parse_result` reads `scores` without checking `failure_class`, `phase`, or
`success`. Two verified consequences:

1. A contaminated or forged high score beats every honest re-run forever (the
   `s4a2` audit found exactly this: a docker-cp-era cell winning dedup into
   the published `score_analysis.json`).
2. A run tagged `verifier_infra_error` that still carries a checkpoint list
   (e.g. P4's un-capped grep scores) **is ingested by `make analyze`** — the
   tag exists on disk but the analysis layer does not honor it. Exclusion is
   currently manual (rescore scripts, run promotion review).

**Rule**: the invariant must hold end-to-end. Tagging a run invalid at scoring
time is necessary but not sufficient; whoever aggregates must filter on
`failure_class`/`success`. Until `analyze_scores.py` does, any headline number
you compute must be accompanied by the sweep below showing zero infra-tagged
runs in its input set.

### P11 — Two scorers, one tested (drift risk)

**Standing hazard** (bead `cdzi`; 2026-07-06 audit finding #5). The
weight-normalized, well-tested `lib/eb_verify/runner.py::CheckpointRunner` is
invoked only by `cli.py` and tests; **production scoring is
`run_task.py::_run_scoring` + `scripts/sandbox/test_runner.sh`**. An integrity
fix landed in the library path silently misses production (the library's
fail-closed Tier-2 fix, commit `4c44cb3`, is parked on
`fix/eb-cdzi-runner-consolidation` — production got its own copy separately).
Full mechanics and the weighting story: `eb-checkpoint-scoring`.

**Rule**: before claiming a scoring fix is live, prove the _production_ path
executes it. "The tests pass" may only mean the dead scorer is fixed.
The consolidation direction (one scorer / CI-oracle / weight-propagation) is
an **open Stephanie decision — PROVISIONAL pending Stephanie**; do not
canonize either path in new code or docs.

### P12 — Optional-dependency validator self-disables

`lib/eb_verify/plugins/__init__.py`: `fact_triples` registers inside
`try/except ImportError` (needs numpy/scikit-learn/jsonschema) and emits a
`RuntimeWarning` when absent; `get_validator("fact_triples")` then returns
`None` (verified in this repo's venv: returns `None`, warning fires). A
dependency-free sandbox silently loses that validator — tasks relying on it
score without it.

**Rule**: a validator that silently doesn't run is a silent misscore waiting
for a task that needs it. If a task's checkpoints require `fact_triples`,
its absence at scoring time must be an infra error for that task, not a skip.

## Doctrine checklist — before you merge any scoring-path change

Scoring path = `run_task.py` scoring/judge/setup functions, `test_runner.sh`,
anything under `lib/eb_verify/`, any `checks/*.sh` template, or
`analyze_scores.py` ingestion.

1. **Every new failure path routes to the infra channel.** Grep your diff for
   the anti-patterns: `return 0.0`, `return {"task_score": 0.0`, bare
   `except ... : continue`, `except Exception: return None` inside scoring
   code. Each one must instead tag `verifier_infra_error` (or set an
   `infra_*` `failure_class`) and keep `success=False`.
2. **No un-capped fallback.** If Tier 2 applies and the judge can't run, the
   run is invalid — never "just use the grep score".
3. **Pristine inputs.** Does your change read anything from the container
   post-agent? Then it is reading agent-controlled data (P7 is not on main).
   Escape it, validate it, or re-copy from host.
4. **Tests ship in the same commit** — P3's `daca3cc` is the precedent for
   what happens otherwise. Existing regression suites to keep green:

   ```bash
   # from repo root; requires `pip install -e lib/` (or use the checked-in venv)
   venv/bin/python -m pytest tests/test_infra_error_classification.py \
       tests/test_llm_judge_artifact_soundness.py -q     # 19 pass at HEAD 7cfb8b0
   venv/bin/python -m pytest tests/security/ -q
   ```

   Full gate is CI's `pytest tests/ -m "not network and not docker"`, not
   `make test` — see `eb-build-and-test`.

5. **Process gate**: production-scoring-path changes are HALT-branch-ready —
   they stop at a ready branch and require Stephanie's explicit sign-off
   before merge. Treat grading-keyword relaxations, task-mix changes, and repo
   repins with the same conservatism — **PROVISIONAL pending Stephanie** (this
   extends the confirmed scoring-path rule to adjacent change types until she
   rules). Dispatch mechanics: `eb-git-and-dispatch-workflow`.
6. **Check the parked branches first.** Before writing an integrity fix, check
   whether it already exists parked: `fix/eb-7jpm-grading-integrity`,
   `fix/eb-wbsq-scoring-gaps(-rebased)`, `fix/eb-cdzi-runner-consolidation`,
   `fix/eb-zafm-verifier-soundness`, `fix/eb-5eq9-preserve-branch-triage`.
   Parked-not-dead: verify bead + branch state before re-landing or
   duplicating — **PROVISIONAL pending Stephanie**.

### The consolidation everyone should know about

The accepted direction for closing this bug class wholesale (the 2026-07-06
audit's "smartest addition", and the spine of `eb-scorer-guard-campaign`) is:

- one shared `scorer_guard(agent_output, verifier_result) -> Score | InfraError`
  used by every scoring entry point, replacing the ~6 hand-rolled guards;
- a `tests/integrity/` adversarial corpus — one failing fixture per confirmed
  vector above (both over-credit and under-credit) — wired into CI as a merge
  blocker.

**Status: open/candidate, NOT landed.** As of 2026-07-07 there is no
`scorer_guard` symbol and no `tests/integrity/` directory in the repo
(verified by grep/ls). Its selection as the campaign spine is **PROVISIONAL
pending Stephanie** (it is the repo's own audit-designated priority, but she
has not confirmed). Do not write code that assumes it exists; do write new
guards so they can collapse into it.

## Detection runbook — auditing existing results

Copy-pasteable, read-only. Run from the repo root.

**Sweep for P5 (broken verifier recorded as success) and count infra-tagged
runs:**

```bash
python3 - <<'EOF'
import json, pathlib
root = pathlib.Path("results/runs")
n = tagged = badsuccess = 0
for p in root.rglob("results.json"):
    try:
        d = json.loads(p.read_text())
    except Exception:
        continue
    n += 1
    if d.get("failure_class"):
        tagged += 1
    if d.get("scores", {}).get("error") and d.get("success") is True:
        badsuccess += 1
        print("P5 HIT:", p)
print(f"results.json: {n}; failure_class tagged: {tagged}; success+scores.error: {badsuccess}")
EOF
```

Baseline on 2026-07-07: `results.json: 491; tagged: 20; success+scores.error: 0`.
Any P5 hit is a run whose number must not be aggregated.

**Sweep for P1 fingerprints (import-loss silent zeros):**

```bash
grep -rl "ModuleNotFoundError" results/runs --include="*.json" | head
# 0 hits on the current tree; any hit = inspect that run's verifier/output.json
```

**Confirm a specific run is on the re-run channel, not scored:**

```bash
python3 -c "import json,sys; d=json.load(open(sys.argv[1])); \
print(d['success'], d['phase'], d['failure_class'])" \
results/runs/<task_id>/<mode>/rep<N>/results.json
# valid measurement:  True complete None
# re-run channel:     False <infra phase> <infra_* or verifier_infra_error>
```

**Before trusting any aggregate**: confirm its input set contains zero
infra-tagged or P5-pattern runs (analyze_scores.py will NOT do this for you —
see P10).

## Provenance and maintenance

Authored 2026-07-07 against working tree `main` @ `7cfb8b0` (local checkout
was 4 commits behind `origin/main`; the delta — `8dcc7fe`, `414651a`,
`f403c2a`, `8a8236f` — lands `.meta` weight sidecars and the P8 awk/JSON
escaping; re-check status markers after pulling). Incident narratives sourced
from commit messages (`git show <sha>`), the regression tests named above, and
the repo's 2026-07-06 deep-audit (local, gitignored report; its findings are
restated here so this skill survives a clean clone).

Re-verify before relying on volatile claims:

```bash
git -C . log -1 --format=%h                          # tree you're auditing vs 7cfb8b0
grep -n "verifier_infra_error" scripts/orchestration/run_task.py   # tag sites still exist
grep -n "return scores" scripts/orchestration/run_task.py | head   # P4 live? (judge-init/continue fallbacks)
sed -n '30,34p;47,51p' lib/eb_verify/plugins/code_patch.py          # P6 live? (except→None/0)
grep -c "json_escape" scripts/sandbox/test_runner.sh                # P8 wbsq escaping present?
grep -n "keep highest" scripts/analyze_scores.py                    # P10 dedup rule unchanged?
grep -rn "scorer_guard" lib scripts tests 2>/dev/null; ls tests/integrity 2>&1  # consolidation landed?
grep -n "_apply_grounded_citations_gate" scripts/orchestration/run_task.py      # P9 gate merged?
git branch -a | grep -E "7jpm|wbsq|cdzi|5eq9|zafm"                  # parked branches still parked?
venv/bin/python -m pytest tests/test_infra_error_classification.py \
    tests/test_llm_judge_artifact_soundness.py -q                   # doctrine tests green?
```

If any of these disagree with this file, the repo wins — update the skill.
