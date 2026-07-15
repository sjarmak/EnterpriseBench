"""
eb_verify — EnterpriseBench centralized verification library.

Single source of truth for all task verification. No per-task copies.

Importing this package must not pull in the plugin stack: ``scorer_guard`` reports
harness failures, so it cannot depend on that stack importing cleanly. Import
submodules directly, e.g. ``from eb_verify.runner import CheckpointRunner``.
"""

__version__ = "0.2.0"
