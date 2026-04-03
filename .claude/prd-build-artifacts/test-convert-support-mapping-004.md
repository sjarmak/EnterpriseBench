# Test Results: convert-support-mapping-004

## CRNT Validation

```
passes_crnt: true
```

- Remove grafana: max_score=0.10 (loses code_paths, ownership, severity) — PASS
- Remove alertmanager: max_score=0.60 (loses ownership, severity, related_issues) — PASS

## Shell Script Syntax

- check_code_paths.sh: OK
- check_ownership.sh: OK
- check_severity.sh: OK
- check_related_issues.sh: OK

## Acceptance Criteria Verification

1. difficulty_stratum = "dual_repo" — YES
2. Two [[repos]] entries (grafana primary, alertmanager dependency) — YES
3. alertmanager URL = "https://github.com/prometheus/alertmanager", rev = "v0.26.0" — YES
4. At least one checkpoint with repo_deps=["grafana"] only (code_paths) and at least one with "alertmanager" (ownership, severity, related_issues) — YES
5. ground_truth.required_files includes entries for both repos — YES (grafana: schedule.go; alertmanager: dispatch.go, notify.go)
6. CRNT passes_crnt=true — YES
7. tool_access expected_mcp_benefit="high" — YES
