"""Adversarial scoring-integrity corpus.

One failing fixture per known score-corruption vector, asserting the scorer
surfaces an infra error (NOT a number) for infrastructure/verifier/judge
failures, in BOTH directions:

* under-credit — a broken verifier / git error must not be recorded as a
  legitimate 0.0;
* over-credit — a judge outage must not leave an un-capped grep score standing.

Wired into the CI gate (see tests/README or pytest config) so the corpus is a
merge blocker on the production scoring path.
"""
