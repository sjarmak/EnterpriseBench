# Configuration Drift: ArgoCD Redis-HA SecurityContext Null Override

## Context

We recently upgraded our Helm version to 3.17.1, and now the ArgoCD HA deployment CI is failing. The `make manifests` step produces a different `upstream.yaml` than what is checked into the repo, causing a diff check to fail.

The ArgoCD HA deployment uses a bundled redis-ha Helm chart located at `manifests/ha/base/redis-ha/chart/`. This chart has its own `values.yaml` that overrides the upstream redis-ha chart defaults.

The error seems related to how Helm 3.17.1 handles null values differently from previous versions — specifically around securityContext fields in the values overrides.

## What I Need

1. **Override hierarchy trace**: Examine the Helm value precedence chain:
   - Upstream redis-ha chart defaults (built into the dependency)
   - ArgoCD's `manifests/ha/base/redis-ha/chart/values.yaml` overrides
   - Rendered manifest output (upstream.yaml)

2. **Drift points**: Identify all places where ArgoCD's value overrides contain `null` values that override upstream defaults. Focus especially on `securityContext` fields, as these are the most likely cause of the Helm 3.17.1 incompatibility.

3. **Expected vs actual**: For each drift point, what does the upstream chart default to, and what does ArgoCD's override set it to? Should the override exist at all, or should it be removed to let the upstream default apply?

4. **Helm version sensitivity**: Explain why this worked under older Helm versions but breaks under 3.17.1.

## Output

Write your findings to `/workspace/argo-cd/DRIFT_REPORT.json` as a JSON object with a `drift_points` array. Each entry needs: `file`, `key`, `expected`, `actual`, and `override_chain`.
