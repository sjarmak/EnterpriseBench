"""The eb_verify root API is restored, but stays lazy.

Bead EnterpriseBench-c7hb9. EnterpriseBench-4t8u8 emptied ``eb_verify/__init__``
of its documented re-exports (``TaskDefinition``/``parse_task``/``CheckpointRunner``/
``compute_score``/``write_reward``) to break the eager coupling that dragged the
validator stack into every ``import eb_verify.scorer_guard``. That fixed the
coupling but silently broke ``from eb_verify import ...`` for out-of-tree tooling,
the CSB-ported harness, and notebooks — EB ships as a public benchmark and those
were the advertised surface.

The restore uses PEP 562 ``__getattr__``: the submodule import fires on attribute
ACCESS, never at package-import time, so both invariants hold at once. This suite
pins all three edges — the API resolves, a bare import pulls nothing, and access
genuinely triggers the load (so the laziness assertion is not vacuous).
"""

from __future__ import annotations

import json

import pytest

from tests.integrity._probe import (
    HEAVY_ROOTS,
    in_package,
    modules_pulled_by,
    run_in_fresh_interpreter,
)

ROOT_API = {"TaskDefinition", "parse_task", "CheckpointRunner", "compute_score", "write_reward"}

# Where a bare ``import eb_verify`` must NOT reach: the re-export targets and the
# registry. Reaching any of them means the re-export went eager again.
LAZY_TARGETS = {"eb_verify.runner", "eb_verify.scoring", "eb_verify.task_parser"}
REGISTRY = "eb_verify.plugins"


def test_root_api_matches_the_submodule_objects() -> None:
    """``from eb_verify import X`` returns the same object as the submodule export."""
    import eb_verify
    from eb_verify.runner import CheckpointRunner
    from eb_verify.scoring import compute_score, write_reward
    from eb_verify.task_parser import TaskDefinition, parse_task

    assert eb_verify.CheckpointRunner is CheckpointRunner
    assert eb_verify.compute_score is compute_score
    assert eb_verify.write_reward is write_reward
    assert eb_verify.TaskDefinition is TaskDefinition
    assert eb_verify.parse_task is parse_task


def test_all_advertised_names_resolve() -> None:
    import eb_verify

    assert set(eb_verify.__all__) == ROOT_API
    for name in eb_verify.__all__:
        assert getattr(eb_verify, name) is not None


def test_unknown_attribute_raises_attributeerror() -> None:
    import eb_verify

    with pytest.raises(AttributeError):
        _ = eb_verify.does_not_exist


def test_bare_import_pulls_neither_the_reexport_targets_nor_the_heavy_stack() -> None:
    """The whole point of 4t8u8: importing the package must stay import-free.

    Run with numpy/sklearn/scipy unimportable, the way a minimal task sandbox is —
    an eager re-export of ``scoring`` would try to import them and crash the probe.
    """
    pulled = modules_pulled_by("eb_verify", block_deps=True)
    leaked = sorted(
        m
        for m in pulled
        if m in LAZY_TARGETS
        or in_package(m, REGISTRY)
        or m.split(".")[0] in HEAVY_ROOTS
    )
    assert not leaked, (
        f"a bare `import eb_verify` pulled {leaked} — the root re-export went eager "
        "again and re-coupled the guard path to the validator stack (4t8u8/b5b6690)."
    )


def test_dir_lists_the_root_api_without_forcing_the_import() -> None:
    """``dir(eb_verify)`` advertises the lazy names but must not eagerly load them.

    ``__dir__`` is part of the same PEP 562 contract as ``__getattr__``: REPL/IDE
    completion calls it, so it must expose the names — but doing so by touching each
    submodule would defeat the laziness the rest of this suite protects.
    """
    out = run_in_fresh_interpreter(
        """
        import sys
        import eb_verify
        names = dir(eb_verify)
        leaked = sorted(m for m in sys.modules if m in (
            "eb_verify.runner", "eb_verify.scoring", "eb_verify.task_parser"))
        import json
        print(json.dumps({"names": names, "leaked": leaked}))
        """
    )
    result = json.loads(out.strip().splitlines()[-1])
    assert ROOT_API <= set(result["names"]), (
        f"dir(eb_verify) omitted part of the root API: missing {ROOT_API - set(result['names'])}"
    )
    assert not result["leaked"], (
        f"dir(eb_verify) eagerly imported {result['leaked']} — __dir__ must stay lazy."
    )


def test_attribute_access_triggers_the_submodule_import_non_vacuity() -> None:
    """Prove the laziness test bites: accessing the attribute DOES load the submodule.

    Without this, ``test_bare_import...`` would pass just as well against a package
    that never exposed the API at all.
    """
    out = run_in_fresh_interpreter(
        """
        import sys
        import eb_verify
        before = set(sys.modules)
        _ = eb_verify.CheckpointRunner
        import json
        print(json.dumps(sorted(set(sys.modules) - before)))
        """
    )
    pulled = set(json.loads(out.strip().splitlines()[-1]))
    assert "eb_verify.runner" in pulled, (
        "accessing eb_verify.CheckpointRunner did not import eb_verify.runner — the "
        "lazy re-export is not actually wired to the submodule."
    )
