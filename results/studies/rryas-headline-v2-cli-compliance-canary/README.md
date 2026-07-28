# Headline v2 CLI compliance canary

This one-shot canary completed successfully and is valid only as operational
treatment-compliance evidence.

The Claude Sonnet 5 CLI arm made 12 authenticated `sgx` calls before completing
the task. Its single receipt proves zero cache reads, zero cache writes, and a
valid isolated launcher scope. Outer-agent spend was $1.931904 against the
authorized $10 ceiling.

The frozen run used agent account 3 and judge account 1. The append-only
receipt, agent trace, run configuration, and injected treatment instruction
are retained, with the core evidence hashes recorded in `study_status.json`.

The task was previously exposed during headline v1 and remains excluded from
headline v2. Its score is not eligible for selection, promotion, or headline
analysis. This canary does not authorize the paid headline v2 matrix.
