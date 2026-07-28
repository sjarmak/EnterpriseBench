# rryas-headline-v1 — Aborted operational run

This capsule is not eligible for headline analysis or promotion.

The fail-closed dispatcher stopped on slot 7 after the CLI arm for
`api-contract-dual-envoy-istio-001` made zero `sgx` calls. The receipt is
classified `infra_invalid` / `infra_sgx_unused`; it cannot be relabeled, scored
as a CLI observation, or retried under the frozen one-attempt v1 protocol.

The run retained seven append-only receipts: six valid slots covering two
complete paired tasks, followed by the invalid CLI slot. Outer-agent spend was
$36.471046. Every receipt proves zero cross-run cache reads and zero cache
writes.

The trace shows an operational prompt conflict. The CLI preamble instructed the
agent to search with `sgx` first, while the task's generic hint emphasized that
both repositories were cloned under `/workspace`. The agent used local
`ls`/`find`/`grep`/`cat` commands exclusively. `sgx` installation and
authentication had passed before the agent started.

The harness now states explicitly that a repository-scoped `sgx` call is
required before inspecting local repository contents, that zero calls invalidate
the run, and that local tools are permitted after the first `sgx` call. This
change is not applied retroactively to v1.

For a new confirmatory capsule, all three touched tasks must be treated as
exposed and excluded:

- `api-contract-grpc-metadata-001`
- `api-contract-grpc-balancer-002`
- `api-contract-dual-envoy-istio-001`

The strengthened contract must first pass a separate operational canary. Any
subsequent confirmatory run needs a new StudySpec, manifest, analysis-plan
population, harness hash, cost envelope, authorization record, and clean output
root.
