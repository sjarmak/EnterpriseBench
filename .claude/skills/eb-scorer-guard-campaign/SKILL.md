---
name: eb-scorer-guard-campaign
description: >
  Executable, decision-gated campaign to consolidate EnterpriseBench's ~6
  hand-rolled score-integrity guards into one scorer_guard(agent_output,
  verifier_result) -> Score | InfraError, plus a tests/integrity/ adversarial
  corpus (over-credit forgery AND under-credit false-zero) wired into CI.
  Load this when: implementing or reviewing scorer_guard; creating or extending
  tests/integrity/; fixing any silent-misscore bug (fake 0.0, un-capped grep
  score, swallowed verifier error); landing the wbsq/7jpm/cdzi integrity
  branches; hardening _run_scoring, _apply_llm_judge, code_patch.validate, or
  test_runner.sh; or writing the paper's scorer-integrity / "survives a
  skeptic" section, the MCP dose-response study, or the parity-audit
  reproducibility story. NOT for general scoring-mechanics questions (use
  eb-checkpoint-scoring), the doctrine statement itself (use
  eb-scoring-integrity-doctrine), or validator plumbing (use
  eb-verification-library).
---

# eb-scorer-guard-campaign — the scorer trust boundary, executed

State as of 2026-07-07, `main` HEAD `7cfb8b0`. Every file:line, command, and
CI observation below was verified against the repo on that date. Re-verify
with the commands in "Provenance and maintenance" before trusting line
numbers — `run_task.py` is the highest-churn file in the repo (42 touches).

This is the campaign skill for the project's designated hardest live problem.
**PROVISIONAL pending Stephanie (Q2):** the scorer_guard consolidation +
`tests/integrity/` adversarial corpus is treated as the accepted campaign
spine because it is the repo's own audit-designated "smartest addition"
(`.gc-reports/audit-2026-07-06.md`, section 1) and hangs directly off the
stated central deliverable: _"a verification pipeline that survives a
skeptic."_ If Stephanie redesignates the hardest problem, this skill's scope
changes.

## When NOT to use this skill

| You want                                                              | Use instead                   |
| --------------------------------------------------------------------- | ----------------------------- |
| What EnterpriseBench is, repo layout, reading route                   | eb-orientation                |
| The integrity invariant and the incident catalog behind it            | eb-scoring-integrity-doctrine |
| How `lib/eb_verify/` validators work, adding a validator              | eb-verification-library       |
| How a task becomes a number today (two scorers, Tier-2 cap)           | eb-checkpoint-scoring         |
| Running one task in Docker, sandbox mechanics                         | eb-sandbox-execution          |
| Getting local tests green the way CI is green                         | eb-build-and-test             |
| How changes are gated/dispatched on this rig (internal orchestration) | eb-git-and-dispatch-workflow  |

## Definitions (each defined once)

- **Silent misscore** — an infrastructure, verifier, or judge failure recorded
  as a real score (usually `0.0`, sometimes an inflated one) instead of an
  error. The repo's dominant bug class.
- **The invariant** — _a score is valid only if the pristine verifier ran on
  real agent output; any infra/verifier/judge failure must surface as
  `verifier_infra_error`, never a `0.0` or an inflated grep score._ Full
  doctrine and incident history: eb-scoring-integrity-doctrine.
- **Pristine verifier** — the verifier content the task author committed, not
  whatever sits in the agent-writable `/workspace` at scoring time. The agent
  can rewrite `test.sh`/verifiers unless they are re-copied or checksummed
  before scoring (vector `7jpm`).
- **Over-credit (forgery)** — an adversarial agent or corrupted pipeline
  produces a higher score than the work merits (e.g. judge outage leaves
  un-capped grep scores; agent rewrites its own verifier).
- **Under-credit (false zero)** — infra failure produces `0.0`
  indistinguishable from a genuinely failing agent (e.g. broken `test.sh`,
  `ModuleNotFoundError`, git error read as "no changes").
- **Tier-1 / Tier-2** — deterministic grep verifiers / LLM judge acting as a
  score _ceiling_: `final = min(grep, judge)`. Tier-2 applies only when the
  task declares `llm_curator` in `verification_modes` and ships
  `expected_solution.json`.
- **Adversarial corpus** — `tests/integrity/`: one test per confirmed attack
  or failure vector, asserting the expected outcome is an infra error or a
  capped score, NOT a plausible-looking number. Does not exist yet (verified
  2026-07-07: `ls tests/integrity` → no such directory).
- **`scorer_guard`** — the target function:
  `scorer_guard(agent_output, verifier_result) -> Score | InfraError`. One
  shared enforcement point replacing the hand-rolled per-site guards. Does not
  exist yet anywhere in `lib/` or `scripts/` (function-shaped design from the
  2026-07-06 audit; the name is the audit's, not yet code).
- **HALT-branch-ready** — this rig's change-control state for production
  scoring-path changes: work stops at a ready branch; Stephanie approves
  before merge; tests ship in the same commit as the fix. Mechanics:
  eb-git-and-dispatch-workflow.

## The mission, in one paragraph

The 2026-07-06 deep audit found that eight historical integrity incidents plus
three bugs still live on `main` are not N unrelated bugs — they are **one
missing invariant enforced inconsistently in ~6 places**, each site getting it
subtly wrong in a different way. The fix is structural: (1) write the failing
adversarial corpus first, (2) extract a single `scorer_guard` used by every
scoring entry point, (3) make the corpus a CI merge blocker. Success is
measurable: a table of vectors × closed tests, both directions (over-credit
and under-credit), all green, with no published number changing un-audited.

---

## 1. Ground-truth state map (verified 2026-07-07 at `7cfb8b0`)

The ~6 guard sites the consolidation replaces. "LIVE" = the bug is on `main`
today. Line numbers drift; re-verify (see Provenance).

| #   | Site                     | Location                                                                          | Failure mode                                                                                                                                                                                                                                                                                                       | Status                                                                                                                                      |
| --- | ------------------------ | --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `_run_scoring`           | `scripts/orchestration/run_task.py:779` (error returns ~802–816)                  | Empty stdout or malformed JSON from `test.sh` returns `{task_score: 0.0, all_passed: False, error: ...}`; **no caller reads `scores["error"]`**; `run_task()` then marks `phase="complete", success=True`. Broken verifier ≡ agent that failed everything.                                                         | LIVE (audit #2)                                                                                                                             |
| 2   | `_apply_llm_judge`       | `run_task.py:847`; fallbacks at ~871–873, ~917–919, ~945–947                      | Three paths silently keep **un-capped grep scores** with only a `logger.warning`: malformed `expected_solution.json`, judge-init failure, per-checkpoint judge exception (bare `continue`). Judge outage ⇒ score inflation. Only the no-agent-output branch (~886–912) correctly routes to `verifier_infra_error`. | LIVE (audit #3)                                                                                                                             |
| 3   | infra-error consumption  | `run_task.py:~1766–1778`                                                          | `scores.get("verifier_infra_error")` is checked **only inside the `llm_curator` branch**. Tier-1-only tasks have no verifier-infra-error channel at all; site 1's error field dead-ends.                                                                                                                           | LIVE (structural)                                                                                                                           |
| 4   | `code_patch` git helpers | `lib/eb_verify/plugins/code_patch.py:32,49` (`_get_diff_stat`, `_get_diff_lines`) | `except (subprocess.TimeoutExpired, Exception): return None` / `return 0` — git missing, permission denied, corrupt `.git` all collapse to "no diff" ⇒ false "No code changes detected" `0.0`. (The tuple is dead code: `Exception` subsumes `TimeoutExpired`.)                                                    | LIVE (audit #4)                                                                                                                             |
| 5   | docker-cp package copy   | `run_task.py:~563–566`                                                            | Copying a directory to a **non-existent** dest copies its _contents_, dropping the `eb_verify` package dir ⇒ in-container `ModuleNotFoundError` ⇒ silent `0.0`. Contaminated 5 published refactor-orchestration runs (`hktt`/`pt0n`).                                                                              | FIXED on main (`16280cf`): the `mkdir -p /workspace/.eb_verify` before `_docker_cp` is **load-bearing, not redundant**. Corpus must pin it. |
| 6   | readability gate         | `run_task.py:1692` (`_assert_agent_readable`) + fail-loud `_chown_to_agent`       | Swallowed chown ⇒ unreadable `instruction.md` ⇒ agent never starts ⇒ fake `success=True, num_turns=0, score=0.0` (`s58f`).                                                                                                                                                                                         | FIXED on main. Corpus must pin it.                                                                                                          |

Adjacent surfaces the guard must be designed with (not necessarily patched by
this campaign, but the corpus covers their vectors):

- `scripts/sandbox/test_runner.sh` (229 lines) — in-container scorer.
  Extracts scores via `grep -oP` from verifier JSON, accumulates with `awk`
  float math. Vector `wbsq`: JSON injection into scoring, including an
  **RCE-via-awk PoC**; escaping fix exists on branch (see §2). Note
  `WORKSPACE="/workspace"` is hardcoded (line 11), not env-overridable —
  local tests must exercise it accordingly or test at the `_run_scoring`
  parse level.
- Pristine re-copy/checksum of grading files before scoring — vector `7jpm`;
  fix on branch (see §2).
- The two-scorer split — production scores via `run_task.py` +
  `test_runner.sh`; the tested `CheckpointRunner.run_all()`
  (`lib/eb_verify/runner.py:335`) is invoked only by `cli.py` and tests
  (audit #5, `cdzi`). **PROVISIONAL pending Stephanie (Q3):** the
  consolidation direction (one scorer / CI-oracle / weight-propagation) is an
  OPEN decision. `scorer_guard` must therefore serve BOTH paths; do not
  design it assuming either scorer wins.
- Grounded-citation gate — absent from `main`, lives on
  `fix/eb-5eq9-preserve-branch-triage` (`pakh`/`dec-f5g`, audit #1). It is
  Stephanie-aware and mayor-owned. Give its vectors (dir-valued citation,
  symlink-escape citation) corpus homes, but do NOT try to land the gate
  itself in this campaign.

## 2. Prior art you MUST reconcile before writing code

**PROVISIONAL pending Stephanie (Q5):** all of these are **parked, not
dead**. Check bead store and branch state before re-implementing anything;
duplicating an unlanded fix creates a merge conflict with a fix Stephanie may
already have approved.

| Branch                                    | Carries                                                                                                        | Relevance                                                                                           |
| ----------------------------------------- | -------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| `fix/eb-wbsq-scoring-gaps` (+ `-rebased`) | `test_runner.sh` JSON/awk escaping; `.meta` weight writes via docker cp; shared container-write helper         | Vectors: awk-RCE, JSON injection. Its tests belong in the corpus.                                   |
| `fix/eb-7jpm-grading-integrity`           | Re-copy/checksum/cross-validate grading files pre-scoring; `/workspace` ownership lock (directory-swap bypass) | Vector: agent rewrites `test.sh`/verifiers.                                                         |
| `fix/eb-cdzi-runner-consolidation`        | Fail-closed Tier-2 no-agent-output in `runner.py`; verifier-soundness repairs                                  | The library-path twin of site 2.                                                                    |
| `feature/eb-1av-unified-scoreresult`      | Vendored `benchmark_qa_core`, emits a unified `ScoreResult`                                                    | A prior structural attempt adjacent to `scorer_guard`'s return type. Read it before choosing `Score | InfraError` representation. |
| `fix/eb-5eq9-preserve-branch-triage`      | The grounded-citation gate                                                                                     | Fenced: mayor-owned, not this campaign.                                                             |

Inspect each in place (read-only):

```bash
cd <repo-root>
git log --oneline main..fix/eb-wbsq-scoring-gaps
git log --oneline main..fix/eb-7jpm-grading-integrity
git log --oneline main..fix/eb-cdzi-runner-consolidation
git log --oneline main..feature/eb-1av-unified-scoreresult
git diff main...fix/eb-wbsq-scoring-gaps -- scripts/sandbox/test_runner.sh
```

Existing test assets to build on (do not duplicate):
`tests/test_infra_error_classification.py` (exit-code → `failure_class`
mapping, the mocking pattern for `run_task.py` internals),
`tests/security/test_check_scripts_injection.py` (injection fixtures, temp
`WORKSPACE` layout), `tests/test_llm_judge_artifact_soundness.py`,
`tests/test_judge.py`.

---

## 3. The campaign

Run phases in order. Each gate states the expected observation; if you see
something else, follow the branch instruction. Do not skip Phase 0.

### Phase 0 — Baseline: know exactly what is red before you add anything

```bash
cd <repo-root>
python3 -m venv .venv-guard && .venv-guard/bin/pip install -q pytest jsonschema tomli && .venv-guard/bin/pip install -q -e lib/
.venv-guard/bin/python -m pytest tests/ --collect-only -q -m "not network and not docker" 2>&1 | tail -3
```

**Expected observation (2026-07-07):** collection is INTERRUPTED with
**6 errors**, split 3 tracked / 3 untracked (this split decides what CI
sees — eb-build-and-test §5 is the home for it):

- **Tracked (CI sees these):** `tests/test_fact_coverage.py`,
  `tests/test_fact_triples_verifier.py` (numpy/scikit-learn optional deps),
  `tests/test_generate_charts.py`.
- **Untracked working-tree files (CI NEVER sees these;
  `git ls-files` on them is empty):**
  `tests/eb_metrics/test_trace_quality_adapter.py` (imports `codeprobe`,
  not in repo), `tests/test_verifier_mutation.py` (imports
  `verifier_mutation_test`, absent from `main`),
  `tests/test_power_analysis.py`. Fixing these repairs the LOCAL baseline
  only.

~3670 tests collect otherwise.

**CI is RED on `main` today because of the 3 TRACKED errors.** Verified
2026-07-07: the last three CI runs (pushes of 07-04, 07-05, 07-06) all
failed at the "Run tests" step in 14–21s with exit code 2 (pytest:
collection interrupted). CI (`.github/workflows/ci.yml`) installs only
`pytest jsonschema tomli` + `pip install -e lib/`, then runs
`python3 -m pytest tests/ -v --tb=short -m "not network and not docker"`.

Consequences you must internalize:

1. "Wire the corpus into CI" costs zero workflow edits — CI already runs all
   of `tests/` — but the corpus is only a _merge blocker_ once the baseline
   collection errors are fixed. Restoring baseline green is in scope for this
   campaign (codebase-ownership rule) but is its own gated step: fixing the
   optional-dep collection errors is a test-infrastructure change (guard
   imports with `pytest.importorskip`, or move heavy imports inside tests);
   it must NOT deselect or `--ignore` scoring tests to get green.
2. The corpus itself must collect and run under CI's minimal dependency set:
   **stdlib + pytest + jsonschema + tomli + eb_verify only.** No numpy, no
   docker, no network. Anything needing a real container gets the `docker`
   marker and a non-CI story — prefer testing the guard function directly
   with mocked `_docker_exec` (the pattern in
   `tests/test_infra_error_classification.py`).

**Gate G0:** you can list the exact baseline failure set and reproduce it
locally. If your local error set differs from the 6 above, the tree moved —
STOP and re-derive before proceeding; do not assume this document.

### Phase 1 — Author the adversarial corpus FIRST (red)

TDD is mandatory here (house rule + the corpus IS the deliverable). Create
`tests/integrity/` with one test per confirmed vector. Both directions must
be represented — a skeptic probes over-credit; an honest benchmark also
refuses to under-credit.

The vector inventory (from the 2026-07-06 audit §1 first-step, cross-checked
against source this session):

| Vector                            | Direction    | What the test asserts                                                                                                                                        | Test strategy (CI-safe)                                                                                                                                                                                                             |
| --------------------------------- | ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| broken-`test.sh`-false-zero       | under-credit | `test.sh` emitting nothing / non-JSON ⇒ outcome is infra error, NOT `task_score: 0.0` with `success=True`                                                    | Call `_run_scoring` with mocked `_docker_exec` returning empty stdout / garbage; assert on the (new) guard outcome                                                                                                                  |
| `ModuleNotFoundError`-silent-zero | under-credit | in-container `eb_verify` import failure ⇒ infra error                                                                                                        | Mock verifier stderr/exit; pin the `mkdir -p` before `_docker_cp` of `EB_VERIFY_LIB` (regression test for `16280cf`)                                                                                                                |
| judge-outage-inflation            | over-credit  | judge init failure / per-checkpoint judge exception / malformed `expected_solution.json` on an `llm_curator` task ⇒ infra error, NEVER un-capped grep scores | Call `_apply_llm_judge` with a judge mock that raises; assert no path returns capless scores silently                                                                                                                               |
| git-error-false-no-changes        | under-credit | git failure in `code_patch` helpers ⇒ `InfraError`, not "No code changes detected"                                                                           | Point `code_patch.validate` at a repo path where git fails (nonexistent dir, corrupt `.git` fixture); today it returns a 0-score result — RED                                                                                       |
| rewrite-`test.sh` (forgery)       | over-credit  | scoring uses pristine grading files: agent-modified `test.sh`/verifier content is detected (re-copy or checksum mismatch ⇒ infra error / rejection)          | Function-level: whatever pristine-check lands (see `fix/eb-7jpm-grading-integrity`); fixture = workspace where grading file bytes ≠ committed bytes                                                                                 |
| awk-RCE / JSON-injection payload  | over-credit  | verifier JSON containing shell/awk metacharacters cannot execute code or forge `"score": 1.0`                                                                | Run `scripts/sandbox/test_runner.sh` against a crafted verifier dir (note hardcoded `WORKSPACE=/workspace` — copy the script into a tmp root or test at `_run_scoring` parse level); payloads from `fix/eb-wbsq-scoring-gaps` tests |
| dir-valued citation               | over-credit  | a citation path that is a directory does not satisfy groundedness                                                                                            | Placeholder until the `pakh` gate lands; write the fixture, mark `xfail(reason="grounded-citation gate not on main")`                                                                                                               |
| symlink-escape citation           | over-credit  | a citation resolving outside the workspace via symlink is rejected                                                                                           | Same `xfail` treatment as above                                                                                                                                                                                                     |
| fake-success no-op run            | under-credit | unreadable `instruction.md` ⇒ fail-loud, never `success=True, num_turns=0, score=0.0`                                                                        | Regression pin for `s58f` via `_assert_agent_readable` behavior                                                                                                                                                                     |

Layout:

```
tests/integrity/
  __init__.py
  conftest.py          # shared fixtures: fake workspace, mocked _docker_exec, crafted verifier JSON
  test_false_zero.py   # under-credit vectors
  test_forgery.py      # over-credit vectors
  test_regression_pins.py  # fixed-on-main incidents (docker-cp mkdir, s58f readability)
```

**Gate G1:** `pytest tests/integrity/ -q` collects cleanly; tests for LIVE
bugs (sites 1–4) FAIL red; regression pins for fixed incidents (sites 5–6)
PASS; grounded-citation vectors are `xfail`. Record the red/green table —
it becomes the paper's vectors × closed-tests table (§4 of this skill).
If a "live bug" test unexpectedly passes: either the bug was fixed since
2026-07-07 (check `git log --oneline -20`) or your test doesn't reach the
guard site — bisect which before continuing.

### Phase 2 — Design `scorer_guard` (no call-site edits yet)

Decisions with obligations:

1. **Home: `lib/eb_verify/`** (e.g. `lib/eb_verify/scorer_guard.py`). Both
   scoring paths can import it: the library path natively; the production
   path already inserts `REPO_ROOT / "lib"` on `sys.path`
   (`run_task.py`, inside `_apply_llm_judge`) and already ships the package
   into containers at `/workspace/.eb_verify` (`PYTHONPATH` in
   `_run_scoring`'s exec line). Do NOT put it in `scripts/` — that
   canonizes the production scorer, which Q3 forbids (PROVISIONAL pending
   Stephanie).
2. **Signature:** `scorer_guard(agent_output, verifier_result) -> Score |
InfraError`. Before inventing the return types, read
   `feature/eb-1av-unified-scoreresult` (vendored unified `ScoreResult`) and
   `TaskRunResult` in `run_task.py` — reconcile, don't create a third score
   shape. `InfraError` must carry `reason`, `stage`, `detail` at minimum:
   that is the shape the existing good branch already writes
   (`scores["verifier_infra_error"]` dict in `_apply_llm_judge`,
   `run_task.py:~899–908`) and the shape `run_task()` consumes at
   `~1766–1778`.
3. **Semantics table** (write it in the module docstring; the corpus is its
   executable form):

   | Input condition                                                                | Outcome                                                                                            |
   | ------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------- |
   | Verifier produced valid JSON from pristine grading files on real agent output  | `Score`                                                                                            |
   | Verifier produced no/invalid output                                            | `InfraError(stage="tier1")`                                                                        |
   | Grading files fail pristine check                                              | `InfraError(stage="pristine")`                                                                     |
   | `llm_curator` task: judge unavailable / errored / expected_solution unreadable | `InfraError(stage="tier2")` — never un-capped grep                                                 |
   | `llm_curator` task: no agent artifact found                                    | `InfraError(stage="tier2", reason="no_agent_output")` (already correct on main — preserve exactly) |
   | Artifact validator hit environment failure (e.g. git error)                    | `InfraError(stage="validator")` — never a 0-score "clean" result                                   |

4. **Failure taxonomy alignment:** production already has
   `failure_class` values `infra_disk|infra_build|infra_clone|
infra_mcp_preflight|infra_auth|infra_perms|infra_oom|infra_timeout|
infra_mcp_config|agent_error` and phases
   `agent_infra_error|verifier_infra_error` (`run_task.py:1542–1737`,
   `1766–1778`). `scorer_guard` outcomes must map into this existing
   taxonomy, not add a parallel one.
5. **No behavioral opinion in the guard about weights or caps.** Weighting
   (equal vs `.meta`) and the `min(grep, judge)` cap are scorer semantics
   owned by eb-checkpoint-scoring's domain; the guard only decides
   _valid-score vs infra-error_. Keep that boundary or the guard becomes a
   third scorer.

**Gate G2:** design reviewed against this table; a written note reconciling
with `feature/eb-1av-unified-scoreresult` exists in the PR/branch
description. This is a production-scoring-path change: from here on the work
is **HALT-branch-ready** (see Phase 5; PROVISIONAL pending Stephanie, Q5:
treat it as requiring her sign-off).

### Phase 3 — Wire call sites one at a time (corpus goes green)

Order by blast radius, smallest first. After each site, run the corpus AND
the site's neighborhood tests; expected observations listed.

| Step | Site                                                                                                                                                                                  | Neighborhood tests                                                          | Expected after wiring                                                                                                                 |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| 3.1  | `code_patch.py` `_get_diff_stat`/`_get_diff_lines` (kill the `except (TimeoutExpired, Exception)` collapse)                                                                           | `pytest lib/eb_verify -q` (this is `make test`), `tests/test_eb_verify_*`   | git-error-false-no-changes test flips green; no other validator behavior change                                                       |
| 3.2  | `_run_scoring` no-output / bad-JSON returns                                                                                                                                           | `tests/test_infra_error_classification.py`, corpus                          | broken-`test.sh` test flips green; a Tier-1-only run with a crashed verifier now ends `phase="verifier_infra_error"`, `success=False` |
| 3.3  | infra-error consumption in `run_task()` — hoist the `verifier_infra_error` check out of the `llm_curator`-only branch                                                                 | corpus + `tests/test_infra_error_classification.py`                         | site-3 structural test green; `phase="complete"` unreachable when any guard fired                                                     |
| 3.4  | `_apply_llm_judge` three fallback paths                                                                                                                                               | `tests/test_judge.py`, `tests/test_llm_judge_artifact_soundness.py`, corpus | judge-outage-inflation tests flip green; the existing no-agent-output branch behavior is byte-for-byte preserved                      |
| 3.5  | pristine re-copy/checksum + `test_runner.sh` escaping — **land by reconciling the existing branches** (`fix/eb-7jpm-grading-integrity`, `fix/eb-wbsq-scoring-gaps`), not by rewriting | `tests/security/`, corpus                                                   | forgery tests flip green                                                                                                              |

Rules for this phase:

- One site per commit; the corpus tests that flip green ship **in the same
  commit** (tests-ship-with-fixes house rule).
- Do not refactor `run_task.py` structurally while wiring (it is 2016 lines,
  2.5× the house max — its size is _why_ these bugs slid through review, per
  audit #8, but a size refactor mid-campaign multiplies review surface;
  file it as a follow-up bead).
- `verifier_timeout` default is 600s (`_run_scoring` signature) — a timeout
  is an `InfraError`, not a score; the existing top-level
  `subprocess.TimeoutExpired → infra_timeout` mapping must keep working.

**Gate G3:** full corpus green except the two grounded-citation `xfail`s;
`pytest tests/ -m "not network and not docker"` shows no NEW failures vs the
Phase-0 baseline; `make test` (library path, `pytest lib/eb_verify -q`)
green.

### Phase 4 — CI wiring and baseline green

1. Fix the Phase-0 collection errors so `tests/` collects cleanly under CI's
   dependency set. **CI repair = the 3 TRACKED files only**
   (`tests/test_fact_coverage.py`, `tests/test_fact_triples_verifier.py`,
   `tests/test_generate_charts.py`): guard their heavy imports with
   `pytest.importorskip`. The 3 untracked files are local-baseline work, not
   CI work — CI never collects them. `tests/test_verifier_mutation.py` is a
   special case, verified 2026-07-07: the TEST file was **never committed
   anywhere** (`git log --all -- tests/test_verifier_mutation.py` is empty —
   it exists only as an untracked working file), while its import target
   `scripts/validation/verifier_mutation_test.py` **IS committed, on
   unlanded branches only** (`2079b2b` "ci: wire verifier soundness gate
   into CI" and `60cd48b`, reachable from
   `fix/eb-cdzi-runner-consolidation`; `git merge-base --is-ancestor
2079b2b main` fails). CI has never seen this test and was never broken by
   it. To fix the local baseline: check the module out from that branch, or
   land both via the cdzi reconciliation (Phase 3.5), or relocate the orphan
   test file with the reason recorded. This matches eb-build-and-test §5.
   Same treatment for `tests/eb_metrics/`'s `codeprobe` dependency (an
   external project, not in this repo). Each fix is its own commit with its
   reason recorded.
2. No workflow edit is required for the corpus (CI already runs
   `pytest tests/`). Optionally add an explicit CI step
   `python3 -m pytest tests/integrity/ -v` so an integrity regression is
   named in the CI UI rather than buried — this is a CI-behavior change;
   include it in the change-control review.

**Gate G4:** a CI run on the campaign branch is fully green (all three
steps: pytest, `scripts/audit_consistency.py`, `bash -n` sweep). Expected
observation: prior to this campaign no `main` push since at least 2026-07-04
has passed the "Run tests" step — your branch being the first green is the
demonstrable baseline repair.

### Phase 5 — Validation and promotion (through change control, never around it)

This campaign touches the production scoring path. Promotion protocol:

1. **Stop at branch-ready.** Do not merge. This is HALT-branch-ready work:
   Stephanie's explicit approval gates the merge. **PROVISIONAL pending
   Stephanie (Q5):** treat the corpus's CI-blocker wiring and any
   `test_runner.sh` change as requiring the same sign-off.
2. **Prove no published number silently changed.** The guard converts some
   historical fake `0.0`s into infra errors; any rescoring of existing runs
   must be an explicit, audited event, not a side effect:
   ```bash
   make analyze     # always re-scans raw runs → results/analysis/score_analysis.json
   git diff --stat  # confirm you have NOT committed regenerated analysis atop old runs
   ```
   Compare headline aggregates before/after on a scratch copy. If any
   promoted/official number moves, follow `docs/RUN_PROMOTION.md` (atomic
   promotion via `scripts/orchestration/run_promotion_orchestrator.py`) and
   surface the delta to Stephanie — precedent: the `hktt` docker-cp bug
   contaminated 5 published runs and required explicit re-runs
   (`results/rerun_pt0n/`).
3. **Success is measurable, never judged by eye:** the deliverable is the
   vectors × tests table — every row in the Phase-1 inventory has a test
   file:line and a green/xfail status; CI green on the branch; zero
   un-audited movement in `results/analysis/score_analysis.json`.
4. Dispatch/process mechanics (beads, direct-dispatch state, who to ping)
   are internal orchestration: see eb-git-and-dispatch-workflow.

---

## Wrong paths — fenced off (each cost real time already, or will)

- **Do not add the guard to `CheckpointRunner`/`scoring.py` only.** That
  path is dead from production's point of view (audit #5, `cdzi`):
  `CheckpointRunner` is invoked only by `eb_verify/cli.py` and tests.
  Production is `run_task.py` + `test_runner.sh`. A cap/guard change landed
  only in the library silently misses every real run.
- **Do not "fix" a failing guard by returning a default score.** Any
  `except: return 0.0` / `return None` / bare `continue` in a scoring path
  is the bug class itself. The only legal fallback is an `InfraError`.
- **Do not delete the `mkdir -p` before `_docker_cp` of the eb_verify lib**
  (`run_task.py:~564`). It looks redundant; it is the `hktt` fix. Docker
  cp'ing a directory to a non-existent destination copies _contents_, not
  the directory.
- **Do not land the grounded-citation gate as part of this campaign.** It is
  on `fix/eb-5eq9-preserve-branch-triage`, Stephanie-aware, mayor-owned
  publish ordering. Corpus rows for its vectors stay `xfail`.
- **Do not rewrite what `fix/eb-wbsq-scoring-gaps` / `fix/eb-7jpm-*` /
  `fix/eb-cdzi-*` already implement.** Parked, not dead (PROVISIONAL, Q5).
  Reconcile and land; their regression tests become corpus rows.
- **Do not change weighting semantics as a drive-by.** At HEAD `7cfb8b0`
  production is equal-weighted (`run_task.py` writes no `.meta` sidecars);
  the fetched `origin/main` changes this by emitting `.meta` weights.
  Weighting mechanics and the stale-on-pull warning are owned by
  eb-checkpoint-scoring §1–§3. Changing weighting is a scoring-semantics
  decision that is Stephanie's (Q3, PROVISIONAL).
- **Do not make CI green by deselecting.** `--ignore`, blanket `skip`, or
  marker abuse on scoring tests hides exactly what this campaign exists to
  expose.
- **Do not trust `make test` as the gate.** It runs `pytest lib/eb_verify
-q` only. The CI bar is `pytest tests/ -m "not network and not docker"`
  plus `scripts/audit_consistency.py` plus the `bash -n` sweep.
- **Do not run benchmark tasks or docker builds to test the guard.** The
  corpus is unit-level by design; a real run costs money and proves less
  than a mocked boundary test.

## Research frontier — what this campaign buys the paper

The project's central deliverable is _"a verification pipeline that survives
a skeptic"_ (`.gc-reports/audit-2026-07-06.md:19`). Everything in this
section is dated 2026-07-07 and labeled by status. **PROVISIONAL pending
Stephanie (Q4):** the publication bar is _prove the result rigorously
whichever sign it has_ — never state a positive MCP lift as fact or as a
precondition.

1. **Scorer integrity as a claimable result (this campaign).** Status: open;
   nothing claimable until Phase 5 completes. The deliverable converts "we
   fixed 8 holes" into "the scorer is provably adversary-resistant in both
   directions": the paper's integrity section becomes the vectors ×
   closed-tests table instead of prose. You have a result when: every
   confirmed vector has a CI-blocking test, both directions are represented,
   and a fresh clone reproduces the table with one command
   (`python3 -m pytest tests/integrity/ -v`).

2. **The MCP parity null (current headline).** Status: measured, defended by
   two symmetric audits. Near-parity across arms — baseline 0.7309 / hybrid
   0.7418 / mcp_only 0.7322 (snapshot recorded in
   `.gc-reports/audit-2026-06-29.md`, from `results/score_analysis.json`).
   The audits attacked it from both sides: `aq8e` (baseline rescore) and
   `uu17` (mcp_only rescore); their one-off audit scripts are checked in at
   repo root (`recompute_headline_aq8e.py`, `rescore_baseline_aq8e.py`,
   `recompute_headline_uu17.py`, `rescore_mcp_only_uu17.py`) with branches
   `audit/eb-aq8e-symmetric-baseline-rescore` and `fix/eb-uu17-mcp-rescore`.
   The null is the honest current state; do not soften it and do not
   apologize for it.

3. **MCP dose-response (the null's rebuttal-of-the-rebuttal).** Status:
   implemented on branch, NOT on `main` (verified:
   `scripts/analysis/mcp_lift_doseresponse.py` does not exist at HEAD;
   branch `feat/eb-wgma-mcp-lift-doseresponse`, commit `c6a8231`). The
   skeptic's objection to any null is "your instrument is blind." The
   rebuttal is pre-registered dose-response: every `task.toml` carries an
   a-priori `expected_mcp_benefit` (high/medium/low); compute per-task delta
   (mcp_only/hybrid − baseline) stratified by expected benefit; test
   monotone trend (Jonckheere–Terpstra, one-sided, conservative under
   ties); anchor with the negative control (calibration tasks spec'd
   `MCP advantage < 0.05`, `docs/ARCHITECTURE.md`) and the positive control
   (CSB's +0.144 fixed-model lift — proof the same instrument detects lift
   when it exists). Both outcomes are publishable; the guard campaign
   strengthens either by closing the "your scorer is broken" attack on the
   underlying deltas. You have a result when: the dose-response lands on
   `main`, runs deterministically from `results/analysis/score_analysis.json`
   with a fixed seed, and its conclusion survives re-running after any
   guard-induced rescore.

4. **Reproducibility bar.** Status: partially built. `make analyze` always
   re-scans raw runs; `make report` consumes an optional
   `results/analysis/reproducibility_report.json` (`generate_report.py`
   reads it; the file does not exist on disk today — treat any
   reproducibility claim as unbacked until it does). Official runs go
   through the atomic promotion pipeline (`docs/RUN_PROMOTION.md`,
   forensic snapshots under `results/official_runs/_failures/`). The bar to
   hold: every published number must be recomputable from raw
   `results/runs/` artifacts by a command in the repo, and every rescore of
   a published number is an audited event with its own script (the
   `aq8e`/`uu17` pattern) — the scorer_guard corpus is what makes those
   recomputations trustworthy.

## Provenance and maintenance

Authored 2026-07-07 against `main` `7cfb8b0` by the retiring-fellow campaign
(discovery: `discovery-enterprisebench.md`, Phase 1). Provisional markers
depend on Stephanie's answers to discovery questions Q2–Q5. One-line
re-verification for every volatile fact:

```bash
# Repo HEAD this skill was verified against
git log -1 --format='%h %s'                               # expect drift; re-verify below if not 7cfb8b0

# Guard-site line anchors (drift-prone; run scripts/check_guard_sites.sh for the full sweep)
grep -n "def _run_scoring\|def _apply_llm_judge" scripts/orchestration/run_task.py   # 779, 847
grep -n "verifier_infra_error" scripts/orchestration/run_task.py                     # tag write ~899; consumption ~1766-1778
grep -n "except (subprocess.TimeoutExpired, Exception)" lib/eb_verify/plugins/code_patch.py  # 32, 49

# scorer_guard / corpus existence (this skill assumes NOT YET BUILT)
grep -rn "def scorer_guard" lib/ scripts/ || echo "not built yet"
ls tests/integrity/ 2>/dev/null || echo "corpus not built yet"

# CI baseline (this skill assumes RED at 'Run tests', exit 2, since >= 2026-07-04)
gh run list --workflow ci.yml --limit 3

# Local collection baseline (this skill assumes 6 errors)
python3 -m pytest tests/ --collect-only -q -m "not network and not docker" 2>&1 | tail -3

# Integrity branches still unlanded (this skill assumes all parked, not dead)
for b in fix/eb-wbsq-scoring-gaps fix/eb-7jpm-grading-integrity fix/eb-cdzi-runner-consolidation feature/eb-1av-unified-scoreresult fix/eb-5eq9-preserve-branch-triage; do echo "== $b"; git log --oneline main..$b | head -2; done

# Two-scorer split still true (CheckpointRunner used only by cli.py/tests)
grep -rln "CheckpointRunner" scripts/ Makefile || echo "still library-only"

# .meta weights still never written by production (true at 7cfb8b0; origin/main writes them — a hit here means the pull landed)
grep -n "\.meta" scripts/orchestration/run_task.py || echo "still equal-weighted in practice"

# Dose-response still branch-only
ls scripts/analysis/mcp_lift_doseresponse.py 2>/dev/null || echo "still not on main"

# Reproducibility report still absent
ls results/analysis/reproducibility_report.json 2>/dev/null || echo "still absent"

# Headline snapshot source
grep -n "0.7309" .gc-reports/audit-2026-06-29.md 2>/dev/null || echo ".gc-reports not present in this clone (gitignored) — headline snapshot unavailable here"
```

Note for public clones: `.gc-reports/` is gitignored (rig-local audit
artifacts) and bead IDs (`hktt`, `wbsq`, `7jpm`, `cdzi`, `apfp`, …) refer to
the maintainer's internal work tracker. The code-level facts in this skill
stand on the repo alone; the audit citations are corroboration, not
load-bearing sources for the commands.
