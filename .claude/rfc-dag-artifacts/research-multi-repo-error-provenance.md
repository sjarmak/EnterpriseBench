# Research: Multi-Repo Error Provenance Tasks

## Existing Pattern Analysis

Studied `err-provenance-dual-docker-001` and `err-provenance-dual-terraform-001` as reference implementations.

### task.toml Structure

- Header comment describing the task
- Top-level fields: `difficulty_stratum`, `mcp_suite`, `repo_set_id`, `org_scale`, `verification_modes`
- `[task]` section: id, suite, task_type, difficulty, estimated_duration_minutes, session_type, description, prompt
- `[[repos]]` sections: url, rev, path, role (primary/upstream/consumer)
- `[metadata]`: languages, total_loc, dependency_depth, frameworks, multi_repo_pattern
- `[[checkpoints]]`: 3 checkpoints (error_source 0.40, error_chain 0.30, trigger_conditions 0.30)
- `[artifacts]`: required = ["answer"]
- `[tool_access]`: expected_mcp_benefit, mcp_benefit_rationale
- `[ground_truth]`: tiers, required_files, sufficient_files

### ground_truth.json Structure

- task_id, task_type, repos array, required_files, sufficient_files
- error_chain: ordered list of propagation steps
- trigger_conditions: list of conditions that trigger the error
- expected_answer field (from acceptance criteria - not in docker example, needs adding)

### instruction.md

- Matches the prompt from task.toml verbatim

### Check Scripts (checks/ directory)

- `check_error_source.sh`: Validates agent found required source files
- `check_error_chain.sh`: Validates agent traced error propagation chain
- `check_trigger_conditions.sh`: Validates agent identified trigger conditions
- All use $WORKSPACE/agent_output/answer.json and $TASK_DIR/ground_truth.json
- All produce JSON output: {score, passed, detail}
- Generic enough to reuse across all error_provenance tasks

### Key Observations

- Check scripts are generic - they work with any ground_truth.json that has the right fields
- Repo roles: primary (user-facing), upstream/consumer (underlying dependency)
- All use difficulty = "hard", session_type = "single"
- Verification modes = ["deterministic"]
- 3 checkpoints with weights: 0.40, 0.30, 0.30

## Target Tasks

1. **Grafana/Prometheus** (Go) - Dashboard query failure traced from Grafana datasource proxy to Prometheus query engine
2. **Celery/kombu** (Python) - Task retry storm from Celery worker to kombu connection pool exhaustion
3. **requests/urllib3** (Python) - SSL verification error from requests to urllib3 certificate handling

All 3 use investigate pattern (trace error across repo boundary).
