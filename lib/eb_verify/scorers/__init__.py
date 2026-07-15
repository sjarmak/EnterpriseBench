"""Standalone ``python -m`` scorers that checkpoint scripts exec directly.

Separate from :mod:`eb_verify.plugins` because the two answer to opposite
constraints. The registry imports all 9 validators at package import so
``runner.py`` can look any of them up; a scorer is run by ``python -m``, which
executes every parent ``__init__`` *before* ``main()`` can catch anything. In the
registry package a scorer therefore inherits the import risk of all 9 validators:
one broken validator empties its stdout, and the runner falls back to fabricating
a score from the exit code -- booking a harness failure as a real agent zero, the
one outcome the scorers exist to avoid.

So this package must stay side-effect-free: no imports here, and nothing that
reaches the registry or the scoring stack (numpy/scikit-learn, which task
sandboxes do not ship). Pinned by
tests/integrity/test_plugin_registration_deps.py.

Scorers are not validators: they return a number, and the registry's
``ValidationResult`` contract has nowhere to put one.
"""
