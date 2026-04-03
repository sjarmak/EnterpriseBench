# Test Results: Multi-Repo Error Provenance Tasks

## All Acceptance Criteria PASSED

### 1. Directory existence

- PASS: err-provenance-dual-grafana-001 exists
- PASS: err-provenance-dual-celery-001 exists
- PASS: err-provenance-dual-requests-001 exists

### 2. Required files (task.toml, ground_truth.json, instruction.md, checks/)

- PASS: All 3 directories contain task.toml, ground_truth.json, instruction.md
- PASS: All 3 directories have checks/ with 3 check scripts each

### 3. task.toml fields

- PASS: All have difficulty_stratum = "dual_repo"
- PASS: All have task_type = "error_provenance"
- PASS: All have multi_repo_pattern = "investigate"
- PASS: All have [[repos]] with real GitHub URLs and release tags

### 4. Real GitHub repos with actual release tags

- grafana-001: grafana/grafana v10.2.0, prometheus/prometheus v2.48.0
- celery-001: celery/celery v5.3.6, celery/kombu v5.3.4
- requests-001: psf/requests v2.31.0, urllib3/urllib3 2.1.0

### 5. Python ecosystem requirement

- PASS: 2/3 tasks use Python (celery + requests)

### 6. ground_truth.json required fields

- PASS: All have task_id, task_type, repos, required_files, expected_answer
