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

from tests.integrity.conftest import LIB, run_in_fresh_interpreter

# Discovered, not hand-maintained: a new module that only imports cleanly when
# something else warms the package first is precisely the bug this guards.
SUBMODULES = sorted(
    ".".join(path.relative_to(LIB).with_suffix("").parts).removesuffix(".__init__")
    for path in (LIB / "eb_verify").rglob("*.py")
    if path.stem != "__main__"
)


@pytest.mark.parametrize("module", SUBMODULES)
def test_submodule_imports_as_the_first_touch_of_the_package(module: str) -> None:
    """Importing any submodule first must not raise -- no import cycles."""
    run_in_fresh_interpreter(
        f"import {module}  # noqa: F401",
        block_deps=False,
        context=(
            f"{module} cannot be imported as the first touch of eb_verify. This is an "
            "import cycle. It must be broken at the layering level (move the shared "
            "primitive down), not papered over by re-adding an eager import that "
            "happens to warm the modules in a working order."
        ),
    )


def test_groundedness_does_not_depend_on_the_plugin_registry() -> None:
    """plugins -> groundedness, never the reverse.

    ``groundedness`` is a deterministic verifier primitive the plugins are built ON
    TOP OF -- four validators import it. Importing the registry from it is a layering
    inversion whether or not it happens to close a cycle, so pin the direction rather
    than only the symptom the test above catches.
    """
    out = run_in_fresh_interpreter(
        """
        import sys
        import eb_verify.groundedness  # noqa: F401
        print("REGISTRY:" + str("eb_verify.plugins" in sys.modules))
        """,
        block_deps=False,
    )
    assert "REGISTRY:False" in out, (
        "importing eb_verify.groundedness pulled in the plugin registry; the "
        "dependency must point one way (plugins -> groundedness), or the cycle "
        "returns the next time an eager import is removed"
    )
