Analyze the latest EnterpriseBench run results, classify failures into actionable categories, and suggest concrete next steps for each failure type.

Use when: after a benchmark run completes, when investigating why tasks failed, or when deciding which tasks to re-run vs. fix.

## Arguments

$ARGUMENTS — optional: `[--results-dir path]` to override the default `results/runs` directory.

## Step 1: Run the Failure Classifier

Run the triage classifier to categorize all task results:

```bash
python3 scripts/triage/triage_run.py --format table
```

If the user provided a `--results-dir` argument, pass it through:

```bash
cd /home/ds/EnterpriseBench && python3 scripts/triage/triage_run.py --format table --results-dir <path>
```

Present the summary table to the user. The categories are:

| Category | Meaning |
|----------|---------|
| pass | Score > 0, task produced useful signal |
| A_infra | Infrastructure failure (Docker, OOM, network, API errors) — re-runnable |
| B_setup | Setup failure (image build, missing deps, clone failures) — fix Dockerfile |
| C_verifier | Verifier failure (checkpoint script bug, parse error) — fix verification |
| D_agent | Agent quality failure (completed but score=0) — review task instructions |
| E_timeout | Task or agent timeout — increase limit or simplify task |

## Step 2: Run Aggregate Breakdown (if available)

Check if `scripts/triage/aggregate_results.py` exists. If it does, run:

```bash
cd /home/ds/EnterpriseBench && python3 scripts/triage/aggregate_results.py
```

Present the suite-level and task-type breakdowns. If the script does not exist yet, skip this step and note that aggregate analysis is not yet available.

## Step 3: Get Detailed JSON for Analysis

Run the classifier again in JSON mode to get structured data for deeper analysis:

```bash
cd /home/ds/EnterpriseBench && python3 scripts/triage/triage_run.py --format json
```

Use the JSON output to build the actionable analysis below. Do NOT print the raw JSON to the user.

## Step 4: Present Actionable Analysis

Organize findings by failure category. For each non-empty category, present:

### A_infra (Infrastructure) — Re-run These

List affected task IDs with their fingerprint labels. These are transient failures that should be retried without changes.

Suggest: `python3 scripts/orchestration/run_task.py <task_id>` for each, or a batch re-run command if multiple tasks are affected.

### B_setup (Setup) — Fix Dockerfiles

List affected task IDs with their fingerprint advice. These need Dockerfile or dependency fixes before re-running.

For each task, identify the relevant Dockerfile or setup script that needs fixing. Point to `scripts/sandbox/dockerfile_generator.py` and the task definition in `benchmarks/` as starting points.

### C_verifier (Verifier) — Fix Checkpoint Scripts

List affected task IDs with their fingerprint advice. These indicate bugs in the verification pipeline, not agent failures.

Point to `lib/eb_verify/plugins/` and the task's checkpoint definitions as places to investigate.

### D_agent (Agent Quality) — Review Instructions

List affected task IDs. These completed without errors but scored 0, indicating the agent did not produce correct output.

For each, suggest reviewing:
- The task instruction clarity in `benchmarks/<suite>/<task_id>/task.json`
- The checkpoint expectations vs. what the agent actually produced
- Whether the ground truth is correct

### E_timeout — Adjust Limits

List affected task IDs. Suggest either:
- Increasing the timeout in the task config or run command
- Simplifying the task if it consistently times out
- Checking if the agent got stuck in a loop (review `agent_stdout.log`)

## Step 5: Recommend Priority Order

Based on the counts, recommend what to tackle first:

1. **B_setup and C_verifier first** — these are benchmark infrastructure bugs that inflate failure rates and mask real signal
2. **A_infra next** — quick wins from re-running with no changes
3. **E_timeout** — check if these are legitimate complexity or configuration issues
4. **D_agent last** — these are the real benchmark signal; only analyze after infra/setup/verifier issues are resolved

End with a one-line summary: "X of Y tasks passing, Z retriable, W need fixes."

## Rules

- Always run from the project root `/home/ds/EnterpriseBench`.
- If no results exist in `results/runs/`, tell the user and suggest running tasks first.
- Do not modify any files — this is a read-only analysis skill.
- Present counts and percentages to give a quick health overview.
- If the user passes `$ARGUMENTS` with `--results-dir`, use that path for both commands.
