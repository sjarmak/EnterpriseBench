# Headline v5 operating boundary

V5 is the immutable successor to the terminal v4 pre-inference failure. V4
batch 1 passed its capacity recheck, but `run_task.py` failed while importing
the harness before agent startup. The sealed v4 record proves that no receipt,
agent output, trace, result, token, cost, or task exposure occurred.

V5 therefore retains the exact v4 population: 31 tasks, 93 sequential slots,
the same three arms and Latin-square order, account 3 Sonnet 5 agent, account 1
isolated Haiku judge, cache-isolation contract, score contract, no-retry policy,
and nine-slot complete-task batches. It changes only the harness revision that:

- makes the standalone child import the repository `lib` package explicitly;
- converts a missing or unreadable appended receipt into a bounded fail-closed
  dispatch error; and
- suppresses raw receipt parse content from chained tracebacks.

The capsule remains `paid_dispatch_authorized: false`. A paid batch requires a
new committed one-shot authorization. Fresh account-specific five-hour and
seven-day utilization must remain below 100%; nonzero utilization is retained
and reported as an accepted provider-load confound. Every started capacity
recheck consumes its authorization, and no retry is implied by this successor.
