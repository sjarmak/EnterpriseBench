# Headline v4 operating boundary

This capsule is locked and remains `paid_dispatch_authorized: false`. It has 31
untouched tasks and 93 sequential slots. The headline arms, accounts, ordering,
cache isolation, and score contract are unchanged from v3.

V4 changes only the judge execution boundary:

- Claude Code runs with `--safe-mode` and no tools.
- The curated judge prompt replaces rather than appends to the default system
  prompt.
- The native per-call judge cap is `$0.10`; the historical successful judge
  cost range was approximately `$0.0011–$0.0021`, while the unisolated v3
  startup-context estimate was `$0.0872411`.
- Judge-account usage remains an explicitly uncovered cost because it is not
  included in the agent process `modelUsage` receipt.

Do not authorize a headline batch until one isolated judge-only canary succeeds
on already-exposed v3 material. The canary must not produce a new agent output
or change task selection. After it passes, generate a committed authorization
artifact; its fixed live provider probes record redacted, hash-bound telemetry
for the account 3 agent and account 1 judge. The observations must be at most
10 minutes old when dispatch starts, both the five-hour and seven-day windows
must remain below 100% utilization, and the exact nine-slot command batch must
remain committed and clean. Nonzero utilization is accepted because these
shared accounts cannot reliably reach a pristine state. Its exact observed
value is a prespecified provider-load confound: retain it with the authorization
and dispatch recheck, report it with the results, and do not claim that provider
load was matched across arms or slots.

Dispatch globally locks both accounts, repeats the live probes after preflight,
writes an exclusive start marker before probing, records the accepted or
rejected redacted recheck, and holds the locks through the batch. Any started
recheck consumes that authorization, including provider errors or exhausted-
account rejection. Up to four one-token Haiku capacity probes (two at
authorization and up to two at dispatch) are uncovered provider usage and must
be included in the authorization disclosure. Every batch still requires fresh
explicit user approval.
