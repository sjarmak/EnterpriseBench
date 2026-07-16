        # api-contract-dual-sqlalchemy-alembic-001

        **Suite:** dependency_management | **Type:** api_contract | **Difficulty:** hard
        **Repos:** sqlalchemy + alembic

        ## Context

        SQLAlchemy 2.0 changed the Session and Connection APIs: `session.execute()`
now requires explicit `text()` wrapping for raw SQL, and the engine/connection
model was restructured. Alembic uses SQLAlchemy internally for migration execution.

Your task:
1. Find where SQLAlchemy 2.0 changed Session and Connection execute APIs
2. Find where Alembic uses SQLAlchemy Session/Connection for migrations
3. Identify breaking contract points between the two
4. Document the impact on Alembic's migration runner

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
