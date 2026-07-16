        # dep-graph-tri-prometheus-alertmanager-grafana-001

        **Suite:** dependency_management | **Type:** dependency_graph | **Difficulty:** expert
        **Repos:** prometheus + alertmanager + grafana

        ## Context

        Prometheus changed its alerting rule evaluation and notification API.
Alertmanager receives alerts from Prometheus, and Grafana reads alert
state from both. Changes in Prometheus' alert format cascade downstream.

Your task:
1. Find where Prometheus defines alert rule evaluation and notification format
2. Find where Alertmanager receives and processes Prometheus alerts
3. Find where Grafana queries Prometheus and Alertmanager for alert state
4. Document the three-way API contract and cascade points

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
