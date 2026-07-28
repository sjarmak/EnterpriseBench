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
or change task selection. After it passes, each headline batch still requires a
fresh 12-slot capacity record, a fresh explicit user approval, a newly generated
authorization artifact, and a committed-clean dispatcher preview.
