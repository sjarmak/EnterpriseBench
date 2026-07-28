# rryas-headline-v2

This paid headline attempt is terminally invalid and must not be promoted.

- Planned slots: 120
- Attempted slots: 23
- Valid slots: 22
- Invalid slots: 1
- Complete paired tasks: 7
- Outer-agent spend: `$95.775424`
- Cross-run cache reads: `0`
- Cache writes: `0`

The fail-closed dispatcher stopped on
`dep-graph-tri-boto3-urllib3-requests-001/cli/rep1/attempt1`. Claude returned
HTTP 429 with `You've hit your session limit · resets 8pm (UTC)`. No retry was
launched and slots 24–120 were not dispatched.

The receipt records `verifier_infra_error` because the missing-artifact judge
path overwrote the earlier `infra_rate_limit` classification. The terminal
status preserves the observed receipt class and the trace-derived root cause.
This telemetry precedence defect must be fixed before another paid matrix.

All eight attempted task IDs are exposed and must be excluded from a new
confirmatory capsule.
