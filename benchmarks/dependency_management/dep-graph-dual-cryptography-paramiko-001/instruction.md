        # dep-graph-dual-cryptography-paramiko-001

        **Suite:** dependency_management | **Type:** dependency_graph | **Difficulty:** hard
        **Repos:** cryptography + paramiko

        ## Context

        The cryptography library v41.0 dropped support for OpenSSL 1.1.1 and
removed the deprecated `default_backend()` parameter. Paramiko uses
cryptography for SSH key exchange and transport encryption.

Your task:
1. Find where cryptography removed default_backend() and changed cipher APIs
2. Find where paramiko calls cryptography APIs for key exchange and encryption
3. Trace the impact through paramiko's transport and kex modules
4. Document which paramiko functions need updating

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
