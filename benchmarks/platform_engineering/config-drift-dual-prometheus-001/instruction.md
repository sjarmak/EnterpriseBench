# Detect config drift between Prometheus TSDB/storage configuration and Thanos sidecar expected settings

Your observability team runs Prometheus v2.48.0 with Thanos v0.32.5 sidecar for
long-term storage and global querying. After a Prometheus upgrade, the Thanos sidecar
started logging warnings about unexpected TSDB configuration and occasionally failing
to upload blocks to object storage.

The root cause is suspected to be configuration drift between Prometheus's TSDB/storage
defaults and what the Thanos sidecar expects from its companion Prometheus instance.

Your task:
1. Examine Prometheus's TSDB and storage configuration defaults in the Go source —
   look for flag defaults, TSDB options structs, and storage retention settings.
2. Examine the Thanos sidecar's expectations for Prometheus configuration — what TSDB
   settings does the sidecar validate or depend on (block duration, retention, WAL
   settings, external labels)?
3. Identify all configuration drift points where Prometheus defaults may conflict with
   Thanos sidecar requirements — particularly around min-block-duration, max-block-duration,
   retention policies, and external label requirements.
4. For each drift point, document the Prometheus default, the Thanos expectation, and
   the failure mode when they diverge.

Write your analysis to /workspace/DRIFT_REPORT.json with:
{
  "drift_points": [
    {
      "config_key": "<configuration parameter>",
      "prometheus_default": "<Prometheus default value>",
      "prometheus_source_file": "<path in prometheus repo>",
      "thanos_expectation": "<what Thanos expects>",
      "thanos_source_file": "<path in thanos repo>",
      "failure_mode": "<what happens when they diverge>",
      "override_chain": ["source -> intermediate -> final"]
    }
  ]
}
