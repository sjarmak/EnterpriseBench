# Configuration Drift: Redis Password Generation Mismatch

## Context

We deployed the bitnami/redis Helm chart with `serviceBindings.enabled=true` and without setting an explicit password (expecting the chart to auto-generate one). After deployment, the Redis server, health checks, and service binding all have DIFFERENT passwords, causing intermittent authentication failures.

Running `helm template` with `--set serviceBindings.enabled=true` and no password produces output where the secret, the configmap health check script, and the ServiceBinding resource contain different password values.

## What I Need

1. **Password flow trace**: Follow how the password is resolved from `values.yaml` through the `redis.password` helper in `_helpers.tpl` to every template that consumes it. List every file that calls `{{ include "redis.password" ... }}` or equivalent.

2. **Drift points**: For each template that consumes the password, identify whether it gets the same or a different value. If different, document the drift.

3. **Root cause**: Explain the Helm mechanism that causes different password values to be generated. This is not a simple typo — it is a fundamental issue with how Helm evaluates template includes.

4. **Override chain**: For each drift point, trace the full resolution path: values.yaml -> helper -> consuming template.

## Output

Write your findings to `/workspace/charts/DRIFT_REPORT.json` as a JSON object with a `drift_points` array and a `root_cause` string. Each drift point needs: `file`, `key`, `expected`, `actual`, and `override_chain`.
