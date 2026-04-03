# Trace Grafana dashboard 'Bad Gateway' datasource proxy error to Prometheus query engine timeout origin

A customer reports that their Grafana dashboard intermittently shows a "Bad Gateway"
error on panels backed by a Prometheus datasource. The raw error visible in the
browser network tab is:

    {"message":"Bad Gateway","status":"bad-gateway"}

The Grafana server logs show:

    logger=datasource.proxy t=2024-01-15T10:23:45Z level=error msg="Data proxy error"
    error="context deadline exceeded" remote_addr=10.0.0.5
    url=/api/datasources/proxy/1/api/v1/query_range

The Prometheus server logs show:

    ts=2024-01-15T10:23:44Z caller=query_logger.go:114 level=warn component=activeQueryTracker
    msg="query timed out" query="rate(http_requests_total{job=~\".*\"}[5m])"

The customer wants to understand why a Prometheus timeout surfaces as a generic
"Bad Gateway" in Grafana rather than a descriptive error about query timeout.

Your task:

1. Find where Grafana's datasource proxy handles outbound HTTP requests to
   Prometheus — trace from the dashboard query API through the proxy middleware.
2. Find where Prometheus's query engine enforces timeouts and returns timeout
   errors — trace through the v1 API query handler to the PromQL engine.
3. Trace the full error propagation chain: Prometheus engine timeout -> HTTP 503
   response -> Grafana proxy receives error -> Grafana formats "Bad Gateway" for
   the frontend. Document each file and function in the chain.
4. Identify why the original timeout context is lost — examine how Grafana's
   proxy translates upstream HTTP errors and whether the Prometheus error body
   is preserved or discarded.

Write your analysis to /workspace/ERROR_PROVENANCE.md with:

- Full error chain (file:function at each step)
- Error origin in Prometheus query engine
- Error translation in Grafana datasource proxy
- Why the original timeout message is lost in translation
