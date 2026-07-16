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
  `$WORKSPACE/instruction.md`, as `_setup_container` does) plus empty repo dirs.
  No `agent_output/`.
- **TASK_DIR** = the real task directory (the answer key).

A no-op leaves the repos pristine; empty repo dirs are the conservative proxy —
any score under empty repos proves the credited evidence came from
`instruction.md` or the answer key, never from the agent. Any check scoring >0
is a leak.

The sweep is CI-enforced by `tests/integrity/test_noop_leak_sweep.py`, which
fails on any leaking checkpoint outside the known-open allowlist.

## Result

```
tasks=116  checks=391  parsed=391  leaks=1
LEAK  1.00  incident_response/ansible-galaxy-tar-regression-prove-001 :: check_root_cause.sh
```

| Task | Checkpoint | Leak mechanism |
|------|-----------|----------------|
| `ansible-galaxy-tar-regression-prove-001` | `root_cause` | `check_root_cause.sh` globs `$WORKSPACE -maxdepth 1 -name "*.md"` and greps the content for root-cause keywords; `instruction.md` (which states the answer) matches → 1.00 with no agent output. Fixed under **EnterpriseBench-hpcsv**. |

All 391 checks return a parseable score (the 14 `eb_verify`-plugin checks import
correctly under `PYTHONPATH=lib` and none default to pass on a missing answer
file).

## Coverage of the repo-source-pristine class

The offline sweep plants empty repo dirs, so it cannot see a check that credits
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
