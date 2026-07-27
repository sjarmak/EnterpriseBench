# Code Finder interface paid pilot

All six prespecified slots ran exactly once. The retrieval and cache-isolation
contracts held in every slot: 12 Code Finder calls (one per repository), no
direct retrieval calls, six unique cache scopes, and zero cross-run cache-read
tokens.

Only two task pairs are quality-eligible. The incident pair is structurally
invalid because its checkpoint scripts require
`/workspace/istio/INCIDENT_REPORT.md`, while both gated arms make the Istio
repository non-writable to the agent. Both agents completed retrieval and wrote
the report to `/workspace/agent_output/INCIDENT_REPORT.md`, but the verifier
scored the missing required path as zero. The immutable receipts retain their
recorded status; `validity_overrides.json` quarantines these scores in analysis.

For the two eligible pairs, MCP scored 0.8545 on average and CLI scored 0.7545,
for a descriptive CLI-minus-MCP difference of -0.1000. CLI used 480,189
combined tokens versus MCP's 636,345 (24.5% fewer), and its reported outer cost
was $1.134167 versus $1.545716 (26.6% lower). Aggregate elapsed time was nearly
identical: 360.337 seconds for CLI and 358.275 seconds for MCP.

The complete pilot cost $6.289727 against a $1.374762 calibration forecast
(4.58x). The excluded incident pair accounted for $3.609844 and 1,254,043
combined tokens. Outer Sonnet usage, not judging, drove the overrun: the Haiku
judge cost only $0.010037 across all attempts. The calibration canary was
therefore not representative of these tasks. Sourcegraph's Finder metadata does
not report inner-agent cost, so the reported dollar totals remain outer-model
plus judge cost only.

This is a descriptive interface pilot, not evidence for promotion or a ranking.
The next paid study must reject gated tasks whose graded artifact path is inside
a gated repository before inference begins.
