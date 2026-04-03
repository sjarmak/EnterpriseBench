# Verify xDS API contract compliance across Envoy proxy, Istio pilot, and go-control-plane

Your service mesh team runs Istio with Envoy sidecars. After upgrading to Istio
1.20 with Envoy v1.28, some services experience intermittent 503 errors during
configuration pushes. The xDS (discovery service) API is the contract between
Istio's pilot (control plane) and Envoy (data plane), with go-control-plane
providing the reference server implementation.

The issue may be caused by xDS API version drift — Envoy v1.28 may expect
xDS v3 resource types that Istio 1.20's pilot sends in a slightly different
format, or go-control-plane's snapshot cache may not handle certain edge cases
that Envoy's xDS client requires.

Your task:

1. Find where Envoy implements the xDS client — locate the ADS (Aggregated
   Discovery Service) client, the resource type URL handling, and the config
   subscription logic. Identify how Envoy validates incoming xDS responses
   and handles version/nonce tracking.
2. Find where Istio pilot generates xDS responses — locate the xDS server,
   the config generation pipeline, and the resource serialization code.
   Identify how pilot constructs CDS, EDS, LDS, and RDS responses.
3. Find where go-control-plane implements the xDS server framework — locate
   the snapshot cache, the ADS stream handler, and the resource versioning
   logic. Identify how it handles type URL registration and resource ordering.
4. Map contract compliance: where do the three implementations diverge in
   xDS protocol handling (version negotiation, resource ordering, type URL
   formats, incremental vs state-of-the-world).

Write your analysis to /workspace/analysis/IMPACT_REPORT.md with:

- Envoy xDS client implementation (file paths)
- Istio pilot xDS server implementation (file paths)
- go-control-plane framework implementation (file paths)
- Contract divergence points
