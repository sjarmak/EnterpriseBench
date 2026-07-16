        # api-contract-dual-envoy-istio-001

        **Suite:** dependency_management | **Type:** api_contract | **Difficulty:** expert
        **Repos:** envoy + istio

        ## Context

        Envoy's xDS (discovery service) API evolved from v2 to v3, changing
resource type names and proto message structures. Istio's control
plane (istiod) generates xDS configuration for Envoy sidecars.

Your task:
1. Find where Envoy defines xDS v3 API proto messages
2. Find where Istio generates xDS configuration for Envoy
3. Identify v2 → v3 API changes in cluster, listener, and route configs
4. Document the contract points between Istio's xDS generator and
   Envoy's xDS consumer

Write your analysis to /workspace/analysis/IMPACT_REPORT.md

        ## Expected Output

        Write your analysis to `/workspace/analysis/IMPACT_REPORT.md`.

        Your report should include:
        - File paths from each repository that are relevant
        - Specific code symbols, functions, or types involved
        - The nature of each change (removal, rename, signature change, behavioral)
        - Migration recommendations

        ## Hints

        - All repos are cloned under `/workspace/`
        - Focus on import/dependency declarations first, then trace into implementation
        - Check version constraints in dependency manifests (Cargo.toml, go.mod, pom.xml, requirements.txt)
