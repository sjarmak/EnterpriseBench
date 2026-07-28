# Headline v3 operating boundary

This capsule is locked and remains `paid_dispatch_authorized: false`. Building,
checking, or previewing it must not dispatch model inference.

The confirmatory matrix contains 32 untouched tasks and three adjacent arms per
task: baseline, generic MCP-only, and CLI. Paid execution is limited to the next
complete four-task block (exactly 12 slots). Batch boundaries are fixed by the
completed receipt prefix and never by observed scores.

Before each paid batch:

1. Confirm that the pinned agent account has capacity for all 12 slots and
   retain a durable capacity-evidence reference.
2. Obtain fresh explicit user approval for that exact batch.
3. Create a new, non-overwriting authorization artifact:

   ```bash
   python3 scripts/studies/authorize_headline_v3_batch.py \
     --plan configs/studies/rryas-headline-v3/dispatch_plan.json \
     --output configs/studies/rryas-headline-v3/dispatch_plan.authorized-<batch>.json \
     --authorization-reference '<approval-reference>' \
     --capacity-reference '<capacity-evidence-reference>'
   ```

4. Review and commit the generated artifact. The dispatcher refuses paid
   execution unless the artifact is tracked, committed, clean, colocated with
   this capsule, and still matches the exact start/end prefix, command hash,
   provider-capacity binding, and spend ceiling.
5. Run the dispatcher with the committed authorized plan:

   ```bash
   python3 scripts/orchestration/headline_study_dispatch.py \
     --plan configs/studies/rryas-headline-v3/dispatch_plan.authorized-<batch>.json \
     --execute
   ```

The repository writer is part of the authorization trust boundary. The
committed-clean check prevents accidental or stale mutation; it is not a
cryptographic attestation against a malicious committer. Never create a real
authorized artifact speculatively, and never reuse one for a later prefix.
