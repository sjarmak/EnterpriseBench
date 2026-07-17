# No-op leak audit (EnterpriseBench-b5vk6)

**Question.** hpcsv found a no-op agent scoring 1.00 on the ansible-galaxy-tar
root-cause checkpoint because a planted `instruction.md` in the agent-visible
tree satisfies the check. Is that planted-evidence / leaked-answer-key pattern
present in OTHER tasks' checkpoints, or is hpcsv the only instance?

**Answer.** hpcsv is the only instance. A no-op agent scores >0 on exactly one
checkpoint across all 116 active tasks / 391 checks. This is a
defensibility-positive result: the systemic concern is closed.

## Method

The real scorer (`scripts/sandbox/test_runner.sh`) runs each checkpoint as
`bash check.sh $WORKSPACE` with `WORKSPACE` and `TASK_DIR` exported. At scoring
time `WORKSPACE=/workspace` holds the agent-visible tree (cloned repos,
`instruction.md`, `agent_output/`) and `TASK_DIR=/workspace/.task` holds the
answer key (`expected_solution.json`, `ground_truth.json`).

`scripts/validation/noop_leak_sweep.py` reproduces the no-op condition offline:

- **WORKSPACE** = a scratch dir containing only `instruction.md` (planted at
  `$WORKSPACE/instruction.md`, as `_setup_container` does). No `agent_output/`
  and no repo source.
- **TASK_DIR** = the real task directory (the answer key).

Each check is run through the shared scorer boundary
(`eb_verify.scorer_guard.run_verifier_subprocess`), so the whole InfraError
ladder (timeout, missing script, path escape, non-JSON output) is defined once by
the codebase rather than re-derived here. A no-op leaves the cloned repos
pristine and writes nothing, so any check that still scores >0 is crediting
`instruction.md` or the answer key, never the agent — that is a leak.

The sweep is CI-enforced by `tests/integrity/test_noop_leak_sweep.py`, which
fails on any leaking checkpoint outside the known-open allowlist, and (since the
b5vk6 review) also on any check that reaches no verdict at all — see the parser
boundary limitation below.

## Faithfulness limitations (reviewed, bounded)

The offline sweep is not a byte-identical replica of in-container scoring. Each
known gap and why it does not move the result:

- **Parser boundary — the one that could hide a leak.** The sweep parses each
  verdict with `json.loads` (via `scorer_guard`), which is STRICTER than the
  `parse_score` awk state machine `test_runner.sh` runs in the production
  container: `parse_score` credits a well-positioned `score` key even when some
  *other* value in the payload is malformed JSON (e.g.
  `{"detail": "gap is 3" x 5" wide", "score": 0.3}` → 0.3, which `json.loads`
  rejects). A check emitting such output under no-op would score >0 in production
  but drop to `errored` (no verdict) here — a false negative. **Empirically this
  does not occur:** all 391 checks emit strictly-valid JSON under the no-op
  condition (`errored=0`), so `json.loads` parses every one and the two parsers
  agree on every leak decision. `test_every_check_scored` freezes `errored == 0`,
  so the moment any check starts emitting malformed no-op output the guard fails
  loudly instead of silently dropping it. Aligning the sweep onto `parse_score`
  itself, so the oracles cannot diverge by construction, is tracked as follow-up
  (**EnterpriseBench-q85op**).
- **Instruction rendering.** Production concatenates an MCP/CLI preamble +
  `instruction_mcp.md` (5 tasks ship one) + the raw `instruction.md` into the
  single `/workspace/instruction.md` the agent sees; the sweep plants only the
  raw `instruction.md` (the baseline rendering). None of the 5 tasks with an
  `instruction_mcp.md` have a check that globs workspace-level `*.md` the way the
  hpcsv `check_root_cause.sh` does — they all gate on `agent_output/` or a named
  report artifact — so the un-planted rendering hides no leak today.
- **cwd and `TASK_DIR` richness.** The sweep runs checks with `cwd=$WORKSPACE`
  and points `TASK_DIR` at the full task dir; production scores from a cwd
  *outside* `$WORKSPACE` and copies only `ground_truth.json` into
  `/workspace/.task`. Both deviations are strictly MORE permissive than
  production, so they can only over-report (false positive), never hide a leak.
  No check globs `$TASK_DIR` (all reads are fixed `ground_truth.json`), so
  neither bites today.

## Result

```
tasks=116  checks=391  errored=0  leaks=1  unexpected=0
LEAK  1.00  incident_response/ansible-galaxy-tar-regression-prove-001 :: check_root_cause.sh
```

`errored=0` is load-bearing: it means every check produced a parseable verdict,
so no check was silently dropped to "not a leak" (see the parser boundary
limitation above).

| Task | Checkpoint | Leak mechanism |
|------|-----------|----------------|
| `ansible-galaxy-tar-regression-prove-001` | `root_cause` | `check_root_cause.sh` globs `$WORKSPACE -maxdepth 1 -name "*.md"` and greps the content for root-cause keywords; `instruction.md` (which states the answer) matches → 1.00 with no agent output. Fixed under **EnterpriseBench-hpcsv**. |

All 391 checks return a parseable score (the 14 `eb_verify`-plugin checks import
correctly under `PYTHONPATH=lib` and none default to pass on a missing answer
file).

## Coverage of the repo-source-pristine class

The offline sweep plants no repo source, so it cannot see a check that credits
*unchanged* cloned source. That class was closed by manual audit of every check
that reads a non-agent `$WORKSPACE` subpath (85 checks): each one gates on an
**agent-written artifact**, absent under a no-op —

- report artifacts written by the agent: `BLAST_RADIUS.md` (dep-traversal, 48),
  `security_audit.md` (7), `INVESTIGATION.md` / `FIX_SUMMARY.md` (chain-err),
  `DRIFT_REPORT.json` (config-drift), `dead_code_report.json` (dead-code, the
  `react/` reads target this file, not React source), `regression_test.py`
  (ansible), `actions.jsonl` (event-replay).

None of these artifacts are planted anywhere in the benchmark tree
(`find benchmarks -name DRIFT_REPORT.json -o -name FIX_SUMMARY.md …` → empty), so
a no-op with pristine repos still fails the artifact-existence gate → 0.0.

## Adjacent finding (not a no-op leak)

`platform_engineering/config-drift-*/check_config_valid.sh` awards `score 1.0`
via a "corrected config not provided (optional — skipped)" branch. It is gated
behind the agent-written `DRIFT_REPORT.json`, so a no-op scores 0 and it is **not**
a defensibility leak — but it is a cheap-credit partial-scoring path (an agent
that files the report and fixes nothing still earns this checkpoint in full).
Tracked separately; out of scope for b5vk6's no-op question.

## Reproduce

```bash
python3 scripts/validation/noop_leak_sweep.py            # human-readable
python3 scripts/validation/noop_leak_sweep.py --json     # machine-readable
python3 -m pytest tests/integrity/test_noop_leak_sweep.py -q
```
