# Research: convert-support-mapping-004

## Current State

- Task: support-map-grafana-alerts-004 in customer_escalation suite
- difficulty_stratum: large_single, single repo (grafana v10.2.0)
- 4 checkpoints: code_paths (0.60), ownership (0.15), severity (0.15), related_issues (0.10)
- Ground truth: grafana ngalert scheduler files (schedule.go, fetcher.go, eval.go, registry.go, alert_rule.go)
- No checks/ directory scripts use repo-specific paths; they operate on agent_output/answer.json generically

## Dual-Repo Pattern (from incident-investigation-dual-flux-001)

- difficulty_stratum = "dual_repo"
- Two [[repos]] entries with role="primary" and role="dependency"
- metadata.dependency_depth = 2, frameworks lists both
- Checkpoints do NOT have repo_deps in the sample (flux task uses fallback heuristic)
- ground_truth.required_files span both repos
- tool_access.expected_mcp_benefit = "high"

## Alertmanager Integration Points

- Grafana v10.2.0 sends alerts to Alertmanager via its API (api/v2/api.go)
- Alertmanager dispatches alerts via dispatch/dispatch.go (routing tree)
- Notification pipeline in notify/notify.go handles delivery
- Silences in silence/silence.go can cause alerts to appear "missing"
- Pin: v0.26.0 (compatible with Grafana v10.2.0)

## CRNT Analysis

With proposed repo_deps:

- code_paths: ["grafana"] (weight 0.60)
- ownership: ["grafana", "alertmanager"] (weight 0.15)
- severity: ["grafana", "alertmanager"] (weight 0.15)
- related_issues: ["alertmanager"] (weight 0.10)

Remove grafana: max_score = 0.10 (only related_issues survives) → passes (<=0.60)
Remove alertmanager: max_score = 0.60 (only code_paths survives) → passes (<=0.60)
CRNT: PASS
