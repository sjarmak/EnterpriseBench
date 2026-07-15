"""Every eb_verify submodule must import standalone, in any order.

An import cycle inside a package is invisible for as long as some *other* eager
import happens to warm the modules in the order that resolves it. That is not a
property to rely on: it makes the package importable by accident, and the accident
breaks the moment an unrelated import is removed.

Each module is imported as the FIRST touch of the package, because that is the only
way to observe the real dependency edges rather than whatever a previously-populated
sys.modules is hiding.
"""

from __future__ import annotations

import pytest

from tests.integrity._probe import (
    LIB,
    in_package,
    modules_pulled_by,
    run_in_fresh_interpreter,
)

# Discovered, not hand-maintained: a new module that only imports cleanly when
# something else warms the package first is precisely the bug this guards.
SUBMODULES = sorted(
    ".".join(path.relative_to(LIB).with_suffix("").parts).removesuffix(".__init__")
    for path in (LIB / "eb_verify").rglob("*.py")
    if path.stem != "__main__"
)

REGISTRY = "eb_verify.plugins"

# The composition root: looking a validator up by artifact type is what ``runner`` is
# FOR, so it is the one module allowed to depend on the registry. Everything else is a
# primitive the registry is built on top of, and must not import upward.
REGISTRY_IMPORTERS = {"eb_verify.runner"}

BELOW_THE_REGISTRY = [
    m for m in SUBMODULES if not in_package(m, REGISTRY) and m not in REGISTRY_IMPORTERS
]


@pytest.mark.parametrize("module", SUBMODULES)
def test_submodule_imports_as_the_first_touch_of_the_package(module: str) -> None:
    """Importing any submodule first must not raise -- no import cycles."""
    run_in_fresh_interpreter(
        f"import {module}  # noqa: F401",
        context=(
            f"{module} cannot be imported as the first touch of eb_verify. This is an "
            "import cycle. It must be broken at the layering level (move the shared "
            "primitive down), not papered over by re-adding an eager import that "
            "happens to warm the modules in a working order."
        ),
    )


@pytest.mark.parametrize("module", BELOW_THE_REGISTRY)
def test_no_module_below_the_registry_imports_the_registry(module: str) -> None:
    """plugins -> everything else, never the reverse.

    Stated over every module rather than for ``groundedness`` alone, where the inversion
    was actually found: the direction is a property of the layering, not of that one
    edge. An inversion that does not happen to close a cycle is silent in the test
    above, and that silence is how this one survived -- it was invisible until the
    eager import that warmed it in a working order was deleted.

    A module that legitimately needs the registry belongs in ``REGISTRY_IMPORTERS``,
    which is a claim about the layering someone has to make on purpose.
    """
    reached = sorted(m for m in modules_pulled_by(module) if in_package(m, REGISTRY))
    assert not reached, (
        f"importing {module} pulled in the plugin registry ({reached}); the dependency "
        f"must point one way (plugins -> {module}), "
        "or the cycle returns the next time an eager import is removed"
    )
