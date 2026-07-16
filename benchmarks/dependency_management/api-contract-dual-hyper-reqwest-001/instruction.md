        # api-contract-dual-hyper-reqwest-001

        **Suite:** dependency_management | **Type:** api_contract | **Difficulty:** hard
        **Repos:** hyper + reqwest

        ## Context

        Between the versions pinned in this workspace, hyper made a breaking
change to how it represents request/response bodies, and reqwest is pinned
to a version that predates that change. The reqwest HTTP client depends
heavily on hyper's body-related types in its client implementation.

Your task:
1. Find where hyper defines its body-related types and traits in this
   version, and work out what changed relative to what reqwest expects.
2. Find where reqwest uses hyper's body type(s) in its client implementation.
3. Identify the contract mismatch between hyper's current body types
   and reqwest's existing usage.
4. Document the migration path for each affected reqwest module, citing the
   specific files, types, and functions involved on both sides.

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
