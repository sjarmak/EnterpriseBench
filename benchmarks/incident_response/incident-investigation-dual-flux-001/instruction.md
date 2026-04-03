# Incident: HelmRelease Stuck in Not-Ready State After Flux Upgrade

## Alert

After upgrading Flux from v2.1 to v2.2, several HelmRelease resources are stuck in a "not ready" state despite the underlying Helm releases being successfully deployed.

## Symptoms

- HelmRelease resources show status `Ready: False` with reason "ArtifactFailed" or "ReconciliationFailed"
- `helm list` shows the releases as deployed successfully
- helm-controller logs show successful reconciliation but Flux reports the HelmRelease as not ready
- The issue affects only HelmReleases that were in-progress during the upgrade
- New HelmReleases created after the upgrade work correctly
- Flux kustomize-controller also cannot see the HelmRelease as ready

## Investigation So Far

The team has identified the general area:

1. Flux v2.2 updated the status condition API for HelmRelease resources
2. helm-controller writes status conditions using the new API format
3. Flux's reconciler reads status conditions to determine readiness
4. HelmReleases that were in-progress during upgrade have old-format conditions
5. The reconciler does not handle the transition from old to new condition format
6. The stale condition causes an infinite reconciliation loop

## Environment

- Flux v2.2.0 at `/workspace/flux2/`
- helm-controller v0.37.0 at `/workspace/helm-controller/`
- Focus on Go code in both repos

## What I Need

1. **Root Cause**: Find where Flux's reconciler evaluates HelmRelease readiness conditions and where helm-controller writes status conditions.

2. **Error Chain**: Trace the failure: old-format status condition -> Flux reconciler cannot parse -> reports not-ready -> triggers re-reconciliation -> infinite loop.

3. **Affected Resources**: Which Flux components and Kubernetes resources are affected?

4. **Remediation**: How should the status condition transition be handled?

## Output

Write your findings to `/workspace/flux2/INCIDENT_REPORT.md`.
