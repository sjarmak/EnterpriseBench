"""Shared probe machinery for the import-graph integrity tests.

These tests assert what a *fresh* process imports. Import state is process-global
and the suite has long since imported numpy, eb_verify.plugins and the rest by the
time it reaches them, so every probe must run in its own interpreter; ``del
sys.modules[...]`` is not a substitute, because any module holding a reference to
the old object keeps it alive.

Deliberately not a conftest: nothing here is a fixture, and pytest is free to load a
conftest under a module identity of its own, so importing one directly can yield two
objects for this file.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from collections.abc import Iterable
from pathlib import Path

LIB = Path(__file__).resolve().parents[2] / "lib"

# The stack whose deferral these tests exist to protect. Spelled once: the blocker
# below and every assertion about "the heavy stack" have to mean the same set, or a
# test passes by asking about a dependency the blocker never removed.
HEAVY_ROOTS = ("numpy", "sklearn", "scipy")

# Refuse to import the heavy stack, the way a minimal task sandbox does: lib's
# pyproject declares only jsonschema, so numpy-less is the canonical install.
BLOCK_HEAVY_DEPS = f"""
    import sys

    BLOCKED = {HEAVY_ROOTS!r}

    class _Blocker:
        def find_spec(self, name, path=None, target=None):
            if name.split(".")[0] in BLOCKED:
                raise ImportError(f"No module named {{name!r}} (numpy-less sandbox)")
            return None

    sys.meta_path.insert(0, _Blocker())
    for _m in [m for m in sys.modules if m.split(".")[0] in BLOCKED]:
        del sys.modules[_m]
"""


def in_package(module: str, package: str) -> bool:
    """True when ``module`` IS ``package`` or lives under it.

    Matched on the dot boundary: a bare ``startswith`` also claims ``eb_verify.pluginsX``,
    so an unrelated module would read as the registry.
    """
    return module == package or module.startswith(package + ".")


def nonstdlib_modules(modules: Iterable[str]) -> set[str]:
    """The subset whose root package is neither stdlib nor a private bootstrap shim.

    This is the unit the import assertions are stated in, because it is what makes an
    allowlist possible: "reaches nothing outside this set" fails on whatever a module
    acquires NEXT, which is the regression worth catching. A denylist of known-bad
    modules is blind to it by construction.
    """
    return {
        m
        for m in modules
        if m.split(".")[0] not in sys.stdlib_module_names
        and not m.split(".")[0].startswith("_")
    }


def run_in_fresh_interpreter(
    body: str,
    *,
    block_deps: bool = False,
    extra_path: Path | None = None,
    context: str = "",
) -> str:
    """Run ``body`` in a new interpreter, optionally with numpy/sklearn unimportable.

    ``extra_path`` is prepended to sys.path, which is how the broken-install tests
    shadow numpy with a module that raises on import. ``context`` is appended to the
    failure message when the probe dies, for callers whose non-zero exit IS the
    finding and needs interpreting.
    """
    prelude = textwrap.dedent(BLOCK_HEAVY_DEPS) if block_deps else ""
    if extra_path is not None:
        prelude += f"sys.path.insert(0, {str(extra_path)!r})\n"
    script = (
        f"import sys\nsys.path.insert(0, {str(LIB)!r})\n"
        + prelude
        + textwrap.dedent(body)
    )
    proc = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=120
    )
    assert proc.returncode == 0, (
        f"probe interpreter died (rc={proc.returncode})\n"
        f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        + (f"\n{context}" if context else "")
    )
    return proc.stdout


def modules_pulled_by(
    module: str, *, block_deps: bool = False, extra_path: Path | None = None
) -> set[str]:
    """Every module a fresh interpreter loads when ``module`` is the first import.

    The delta is captured before the probe imports anything of its own, so a module the
    probe needs cannot mask the same import in the subject. Callers state their invariant
    as a set operation on the result rather than each parsing a stdout key of its own.
    """
    out = run_in_fresh_interpreter(
        f"""
        import sys
        before = set(sys.modules)
        import {module}  # noqa: F401
        pulled = sorted(set(sys.modules) - before)
        import json
        print(json.dumps(pulled))
        """,
        block_deps=block_deps,
        extra_path=extra_path,
    )
    return set(json.loads(out.strip().splitlines()[-1]))
