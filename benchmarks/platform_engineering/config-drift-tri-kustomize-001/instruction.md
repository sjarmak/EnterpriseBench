# Detect configuration drift in strategic merge patch handling across Kustomize, ArgoCD, and Flux

Your platform team uses a GitOps stack: Kustomize for overlay management, ArgoCD
for application delivery, and Flux for HelmRelease reconciliation. After upgrading
all three tools, you notice that strategic merge patches applied via Kustomize
overlays are being handled differently by ArgoCD's sync engine and Flux's
Kustomize controller.

Specifically, list-type strategic merge patches (e.g., container env vars, volume
mounts) produce different merge results depending on which tool processes them.
ArgoCD's resource tracking and diff normalization may strip or reorder fields that
Kustomize preserves, while Flux's Kustomize controller may apply patches in a
different order than standalone Kustomize.

Your task:

1. Find where Kustomize implements strategic merge patch logic — locate the patch
   transformer and the strategic merge patch library it delegates to. Identify how
   list merge keys (e.g., `name` for containers, `mountPath` for volumeMounts) are
   resolved.
2. Find where ArgoCD normalizes resources during sync diff — locate the diff/
   normalizer and the resource tracking annotation logic. Identify how ArgoCD's
   normalizer handles list-type fields differently from raw Kustomize output.
3. Find where Flux's kustomize-controller applies overlays — locate the build logic
   and identify any differences in how it invokes the Kustomize API vs the standalone
   `kustomize build` CLI.
4. Document all drift points where the three tools diverge in merge behavior.

Write your analysis to /workspace/DRIFT_REPORT.json with:
{
"drift_points": [
{
"config_key": "<merge behavior or config parameter>",
"kustomize_behavior": "<behavior in kustomize>",
"kustomize_source_file": "<path in kustomize repo>",
"argocd_behavior": "<behavior in argo-cd>",
"argocd_source_file": "<path in argo-cd repo>",
"flux_behavior": "<behavior in flux2>",
"flux_source_file": "<path in flux2 repo>",
"impact": "<potential impact of this drift>"
}
]
}
