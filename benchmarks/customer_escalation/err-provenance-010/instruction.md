# Support Ticket: Grafana crashes when querying non-existent Jaeger trace

**Priority:** Medium
**Submitted by:** Observability Engineer
**Product:** Grafana (Jaeger datasource)

---

Hi,

When we query for a trace ID that doesn't exist or has expired in our Jaeger backend, Grafana returns a 500 Internal Server Error instead of a "trace not found" message. The Grafana server logs show:

```
runtime error: index out of range [0] with length 0
```

This happens specifically with the Jaeger datasource plugin. If we query an existing trace, it works fine. But any trace ID that returns an empty result from the Jaeger API causes this panic.

Our monitoring dashboards link to trace IDs that may have expired, so this is a common scenario for us.

We need to find:
1. Where in the Grafana source code the Jaeger datasource client accesses the trace response
2. Which specific code path panics when the response is empty (what array access is missing a bounds check?)
3. How the panic propagates to become a 500 error visible to the user

The repository is available under `/workspace/grafana/`.

Thanks,
Drew
