        # dep-graph-dual-junit-mockito-001

        **Suite:** dependency_management | **Type:** dependency_graph | **Difficulty:** hard
        **Repos:** junit5 + mockito

        ## Context

        JUnit 5 replaced JUnit 4's `@RunWith` runner mechanism with the
`@ExtendWith` annotation and a different extension/callback model for
hooking into test lifecycle events. Mockito's JUnit 4 integration (a runner
class that wires mock injection into a test run) does not carry over
automatically — Mockito ships a separate module implementing JUnit 5's
model, but the class doing that integration, and how its lifecycle behavior
differs from the JUnit 4 version, has to be found in the code.

Your task:
1. Find where JUnit 5 defines the extension interface and the lifecycle callback interfaces used for per-test setup/teardown hooks
2. Find where Mockito implements its JUnit 5 integration module and identify the class that does the work
3. Identify the API contract differences between Mockito's JUnit 4 integration mechanism and the JUnit 5 integration class you found
4. Document how a test class should be migrated from Mockito's JUnit 4 integration to its JUnit 5 integration, naming the specific old and new classes involved on each side

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
