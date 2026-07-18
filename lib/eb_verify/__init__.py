"""
eb_verify — EnterpriseBench centralized verification library.

Single source of truth for all task verification. No per-task copies.

Importing this package must not pull in the plugin stack: ``scorer_guard`` reports
harness failures, so it cannot depend on that stack importing cleanly. And because
importing any submodule runs this ``__init__`` first, an *eager* re-export here
would drag the validators (+ jsonschema) into every ``import eb_verify.scorer_guard``
— the 22-module coupling EnterpriseBench-4t8u8 removed.

The documented root API is therefore restored LAZILY via PEP 562 ``__getattr__``:
the submodule import fires only on attribute access, so ``import eb_verify`` and the
scorer_guard path stay import-free, while out-of-tree tooling keeps the advertised
surface (``from eb_verify import CheckpointRunner`` etc.). Prefer the direct submodule
import in new in-tree code; these exist for downstream stability.
"""

import importlib

__version__ = "0.2.0"

# Public root API: attribute -> (submodule, name-in-submodule). Resolved lazily so
# that importing the package — or any submodule, which runs this __init__ first —
# pulls in nothing beyond stdlib.
_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "TaskDefinition": ("eb_verify.task_parser", "TaskDefinition"),
    "parse_task": ("eb_verify.task_parser", "parse_task"),
    "CheckpointRunner": ("eb_verify.runner", "CheckpointRunner"),
    "compute_score": ("eb_verify.scoring", "compute_score"),
    "write_reward": ("eb_verify.scoring", "write_reward"),
}

# Derived from _LAZY_EXPORTS so the advertised surface can never drift from what
# actually resolves (dict insertion order is guaranteed since 3.7).
__all__ = list(_LAZY_EXPORTS)


def __getattr__(name):
    """PEP 562 lazy resolver for the documented root API.

    Fires only when ``name`` is not already a real attribute/submodule, so it never
    shadows ``eb_verify.cli`` and friends, and never runs at package-import time.

    Deliberately unannotated: ``eb_verify.__init__`` must add zero import side effects
    (``tests/integrity/test_plugin_registration_deps.py`` pins this — it is the whole
    point of EnterpriseBench-4t8u8), and a ``-> Any`` return type would pull ``typing``
    into every ``import eb_verify``.
    """
    try:
        module_name, attr = _LAZY_EXPORTS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None

    value = getattr(importlib.import_module(module_name), attr)
    globals()[name] = value  # cache: subsequent access skips __getattr__ entirely
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *_LAZY_EXPORTS})
