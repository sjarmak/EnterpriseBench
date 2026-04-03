# Map Grafana dashboard 'execution exceeded' query timeout to Prometheus query engine code

A customer support ticket reports:

    "Our Grafana dashboard panels are showing 'Error: query timeout' for panels
    with complex PromQL queries. The error message is: 'query processing would
    load too many samples into memory in query execution'. This started after we
    upgraded Prometheus to v2.48.0. Simple queries work fine."

Your task is to map this user-reported issue from the Grafana UI all the way down
to the Prometheus query engine code that enforces the limit.

Your task:
1. Find where Grafana surfaces this error to the user — trace from the dashboard
   panel rendering code through the data source proxy to the Prometheus data source
   plugin.
2. Find where Prometheus generates the "query processing would load too many samples"
   error — identify the query engine code that enforces sample limits.
3. Map the complete path: Prometheus query engine limit → HTTP API error response →
   Grafana data source proxy → panel error display.
4. Identify the configuration parameters in both Grafana and Prometheus that control
   this behavior (query timeout, max samples, step interval).

Write your analysis to /workspace/SUPPORT_MAPPING.md with:
- Grafana code path for error display (file:function)
- Prometheus query engine limit code (file:function)
- Complete error path between the two
- Configuration knobs the customer can adjust
