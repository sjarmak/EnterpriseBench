# Detect config drift between ArgoCD application controller defaults and argo-helm chart values.yaml overrides

Your platform team deploys ArgoCD using the official argo-helm Helm chart. After
upgrading to ArgoCD v2.9.0 with argo-helm chart version argo-cd-5.51.0, resources
that were adopted by an Application before the migration are being reported as
out-of-sync, and pruning is not behaving as expected.

Investigation suggests configuration drift between the ArgoCD application
controller's built-in defaults and what the Helm chart writes into the ArgoCD
ConfigMaps. The chart may be setting values that differ from the controller's
compiled-in defaults, so a cluster installed by the chart does not behave like a
cluster running stock defaults.

Your task:
1. Examine the ArgoCD controller's built-in default configuration values in the Go
   source (default constants, ConfigMap keys, and flag defaults). Note where a
   default is used as a fallback when a ConfigMap key is absent or empty.
2. Examine the argo-helm chart's values.yaml for the argo-cd chart, including the
   sections that populate the ArgoCD ConfigMaps.
3. Identify every configuration key where the value the chart ships differs from
   the controller's built-in default. Report only differences you can prove from
   both sides: cite the Go source that establishes the default AND the values.yaml
   key that overrides it.
4. If a setting the chart appears to override in fact matches the controller
   default, do NOT report it as drift.
5. For each real drift point, document: the ArgoCD default (with source file), the
   Helm override (with values.yaml path), and the potential impact.

Write your analysis to /workspace/DRIFT_REPORT.json with:
{
  "drift_points": [
    {
      "config_key": "<configuration parameter>",
      "argocd_default": "<default value from Go source>",
      "argocd_source_file": "<path in argo-cd repo>",
      "helm_override": "<value in Helm chart>",
      "helm_source_path": "<values.yaml key path>",
      "impact": "<potential impact of this drift>",
      "override_chain": ["source -> intermediate -> final"]
    }
  ]
}
