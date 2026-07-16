        # config-drift-dual-setuptools-pip-001

        **Suite:** platform_engineering | **Type:** config_drift | **Difficulty:** expert
        **Repos:** setuptools + pip

        ## Context

        setuptools 67.0 deprecated pkg_resources in favor of importlib.metadata.
pip vendors its own copy of pkg_resources and uses it for metadata
resolution, entry point discovery, and namespace package handling.

Your task:
1. Find where setuptools deprecated/changed pkg_resources APIs
2. Find where pip vendors and uses pkg_resources internally
3. Identify which pip features depend on deprecated pkg_resources behavior
4. Document the drift between setuptools' intended migration path and
   pip's vendored copy

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
