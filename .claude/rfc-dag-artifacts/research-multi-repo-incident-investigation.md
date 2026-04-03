# Research: Multi-Repo Incident Investigation Tasks

## Existing Format Analysis

### task.toml Structure

- Top-level fields: `difficulty_stratum`, `mcp_suite`, `repo_set_id`, `org_scale`, `verification_modes`
- `[task]` section: id, suite, task_type, difficulty, estimated_duration_minutes, session_type, description, prompt
- `[[repos]]` sections: url, rev, path, role (primary/dependency/upstream/intermediary)
- `[metadata]`: languages, total_loc, dependency_depth, frameworks, multi_repo_pattern
- `[[checkpoints]]`: name, weight, verifier, description, timeout_seconds (weights must sum to 1.0)
- `[artifacts]`: required (incident_report for incident tasks), optional
- `[tool_access]`: expected_mcp_benefit, mcp_benefit_rationale
- `[ground_truth]`: tiers, required_files, sufficient_files

### ground_truth.json Structure

- task_id, task_type, repos (array of {url, rev, path})
- required_files (array of {path, repo, confidence, source})
- sufficient_files (array)
- Task-specific fields: error_chain, root_cause, affected_services, remediation, etc.
- expected_answer (needed per acceptance criteria)

### Check Scripts Pattern

- Bash scripts reading from `$WORKSPACE/` and `$TASK_DIR/`
- Output JSON: `{"score": N, "passed": bool, "reason": "..."}`
- For incident_report artifact: read from `$WORKSPACE/{repo}/INCIDENT_REPORT.md`
- Use grep -qiE patterns to match key concepts
- Score = found/total, passed threshold typically >= 50%

### instruction.md

- Mirrors the prompt from task.toml in markdown format
- Provides additional context, symptoms, environment details
- Specifies output file location

### Naming Convention

- incident-investigation-{stratum}-{ecosystem}-{number}
- e.g., incident-investigation-dual-istio-001

### Multi-Repo Patterns (from schema)

- propagate, investigate, enforce, orchestrate
- "investigate" most common for incident tasks (3 of 5 required)
