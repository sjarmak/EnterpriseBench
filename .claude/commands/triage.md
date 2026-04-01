Analyze the latest EnterpriseBench run results, classify failures into actionable categories, and suggest concrete next steps for each failure type.

Use when: after a benchmark run completes, when investigating why tasks failed, or when deciding which tasks to re-run vs. fix.

## Arguments

$ARGUMENTS — optional flags:
- `--results-dir <path>` — override the default `results/runs` directory
- `--suite <name>` — filter to a specific suite (substring match, e.g. `customer_escalation`)
- `--task-type <name>` — filter to a specific task type (substring match, e.g. `error_provenance`)
- `--category <cat>` — filter to a specific triage category: `pass`, `A_infra`, `B_setup`, `C_verifier`, `D_agent`, `E_timeout`

Multiple filters can be combined.

## Step 1: Run the Failure Classifier

Run the triage classifier to categorize all task results. Build the command from the arguments provided.

Base command:

```bash
cd /home/ds/EnterpriseBench && python3 scripts/triage/triage_run.py --format table
```

Append any filter flags the user provided. Examples:

```bash
# All failures in customer_escalation suite
cd /home/ds/EnterpriseBench && python3 scripts/triage/triage_run.py --format table --suite customer_escalation

# Only agent quality failures
cd /home/ds/EnterpriseBench && python3 scripts/triage/triage_run.py --format table --category D_agent

# Error provenance tasks that failed
cd /home/ds/EnterpriseBench && python3 scripts/triage/triage_run.py --format table --task-type error_provenance --category D_agent

# Custom results directory
cd /home/ds/EnterpriseBench && python3 scripts/triage/triage_run.py --format table --results-dir results/smoke_hybrid_v4
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

## Step 2: Run Aggregate Breakdown

Run the aggregate analysis for suite-level and task-type breakdowns:

```bash
cd /home/ds/EnterpriseBench && python3 scripts/triage/aggregate_results.py
```

If the user provided `--results-dir`, pass it through:

```bash
cd /home/ds/EnterpriseBench && python3 scripts/triage/aggregate_results.py --results-dir <path>
```

Present the suite-level pass rates and task-type breakdowns. Highlight any suite or task type with pass rate below 70%.

## Step 3: Get Detailed JSON for Analysis

Run the classifier again in JSON mode to get structured data for deeper analysis:

```bash
cd /home/ds/EnterpriseBench && python3 scripts/triage/triage_run.py --format json
```

Pass through any filter flags from Step 1. Use the JSON output to build the actionable analysis below. Do NOT print the raw JSON to the user.

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
- If the user passes `$ARGUMENTS`, parse out recognized flags (`--results-dir`, `--suite`, `--task-type`, `--category`) and pass them to both triage_run.py and aggregate_results.py where applicable.
