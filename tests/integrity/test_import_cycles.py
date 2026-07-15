"""Every eb_verify submodule must import standalone, in any order.

An import cycle inside a package is invisible for as long as some *other* eager
import happens to warm the modules in the order that resolves it. That is not a
property to rely on: it makes the package importable by accident, and the accident
breaks the moment an unrelated import is removed.

Concretely, ``eb_verify.groundedness`` and the plugin registry used to form a cycle
(groundedness -> plugins/__init__ -> incident_report -> groundedness). It never
fired, because ``eb_verify/__init__`` eagerly imported ``runner`` -> ``plugins``,
so ``plugins`` was always fully initialized before anything could reach
``groundedness`` first. Deleting those (dead, zero-consumer) re-exports removed the
accidental ordering and the cycle surfaced immediately -- as an ImportError on the
first process to touch ``groundedness`` before ``plugins``, which is exactly what
``run_task.py`` does on its ``require_grounded_citations`` path.

Each module is imported as the FIRST touch of the package in a fresh interpreter,
because that is the only way to observe the real dependency edges rather than
whatever a previously-populated sys.modules is hiding.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parents[2] / "lib"

# Every importable submodule of eb_verify. Deliberately a discovered list rather
# than a hand-maintained one: a new module that only imports cleanly when
# something else warms the package first is precisely the bug this guards.
SUBMODULES = sorted(
    f"eb_verify.{path.stem}"
    for path in (LIB / "eb_verify").glob("*.py")
    if path.stem not in ("__init__", "__main__")
)


@pytest.mark.parametrize("module", SUBMODULES)
def test_submodule_imports_as_the_first_touch_of_the_package(module: str) -> None:
    """Importing any submodule first must not raise -- no import cycles."""
    proc = subprocess.run(
        [sys.executable, "-c", f"import sys; sys.path.insert(0, {str(LIB)!r}); import {module}"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, (
        f"{module} cannot be imported as the first touch of eb_verify:\n{proc.stderr}\n"
        "This is an import cycle. It must be broken at the layering level (move the "
        "shared primitive down), not papered over by re-adding an eager import that "
        "happens to warm the modules in a working order."
    )


def test_groundedness_does_not_depend_on_the_plugin_registry() -> None:
    """The specific edge that was inverted: a primitive must not import the registry.

    ``groundedness`` is a deterministic verifier primitive that the plugins are built
    ON TOP OF -- four validators import it. It reaching back up into
    ``eb_verify.plugins`` for a file-reading helper is what closed the loop. Pinning
    the direction here keeps the parametrized test above from silently regressing to
    "passes because someone re-added an eager import somewhere".
    """
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import sys; sys.path.insert(0, {str(LIB)!r}); "
            "import eb_verify.groundedness; "
            "print('eb_verify.plugins' in sys.modules)",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, f"groundedness failed to import:\n{proc.stderr}"
    assert proc.stdout.strip() == "False", (
        "importing eb_verify.groundedness pulled in the plugin registry; the "
        "dependency must point one way (plugins -> groundedness), or the cycle "
        "returns the next time an eager import is removed"
    )
