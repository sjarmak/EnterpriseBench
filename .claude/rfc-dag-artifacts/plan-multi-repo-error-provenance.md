# Plan: Multi-Repo Error Provenance Tasks

## Task 1: err-provenance-dual-grafana-001

**Repos:** grafana/grafana (v10.2.0) + prometheus/prometheus (v2.48.0)
**Scenario:** Dashboard query returns "Bad Gateway" / datasource proxy error when PromQL query hits Prometheus query engine timeout
**Error chain:** User sees Grafana dashboard error -> Grafana datasource proxy -> HTTP client to Prometheus -> Prometheus query engine evaluates and times out -> error propagates back
**Key files:**

- Grafana: pkg/api/datasource_proxy.go, pkg/tsdb/prometheus/prometheus.go
- Prometheus: web/api/v1/api.go, promql/engine.go
  **Languages:** Go + Go

## Task 2: err-provenance-dual-celery-001

**Repos:** celery/celery (v5.3.6) + celery/kombu (v5.3.4)
**Scenario:** Celery task retry storm caused by kombu connection pool exhaustion; worker logs show "ConnectionResetError" / "Too many connections"
**Error chain:** Celery worker executes task -> task raises exception -> retry mechanism fires -> kombu tries to publish retry message -> connection pool exhausted -> connection reset error propagates back to worker
**Key files:**

- Celery: celery/app/task.py, celery/worker/request.py
- Kombu: kombu/connection.py, kombu/transport/pyamqp.py
  **Languages:** Python + Python

## Task 3: err-provenance-dual-requests-001

**Repos:** psf/requests (v2.31.0) + urllib3/urllib3 (v2.1.0)
**Scenario:** SSL certificate verification failure; user gets "SSLError: HTTPSConnectionPool" when connecting to internal CA-signed endpoint
**Error chain:** User calls requests.get() -> requests creates session -> urllib3 HTTPSConnectionPool -> ssl_wrap_socket -> certificate verification fails -> SSLError wraps and propagates back
**Key files:**

- Requests: requests/adapters.py, requests/models.py
- urllib3: urllib3/connectionpool.py, urllib3/util/ssl\_.py
  **Languages:** Python + Python

## Implementation Steps

For each task:

1. Create directory under benchmarks/customer_escalation/
2. Create task.toml following docker example pattern
3. Create ground_truth.json with required_files, error_chain, trigger_conditions, expected_answer
4. Create instruction.md matching the prompt
5. Create checks/ directory with check_error_source.sh, check_error_chain.sh, check_trigger_conditions.sh (copied from docker example - they are generic)

## Verification

- Confirm all 3 directories exist with all required files
- Validate task.toml fields match acceptance criteria
- Confirm check scripts are executable
