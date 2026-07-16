        # dep-graph-tri-boto3-urllib3-requests-001

        **Suite:** dependency_management | **Type:** dependency_graph | **Difficulty:** expert
        **Repos:** urllib3 + requests + botocore

        ## Context

        urllib3 2.0 was a major release that affected the entire Python HTTP
stack. Both requests and botocore depend on urllib3 with conflicting
version constraints. botocore vendors its own urllib3 copy.

Your task:
1. Map the dependency chain: boto3/botocore → urllib3, requests → urllib3
2. Find version pin conflicts between botocore and requests for urllib3
3. Identify where botocore's vendored urllib3 diverges from upstream 2.0
4. Document the upgrade coordination challenge across all three repos

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
