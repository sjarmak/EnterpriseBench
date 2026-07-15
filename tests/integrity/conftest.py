"""Shared probe machinery for the import-graph integrity tests.

These tests assert what a *fresh* process imports. Import state is process-global
and the suite has long since imported numpy, eb_verify.plugins and the rest by the
time it reaches them, so every probe must run in its own interpreter; ``del
sys.modules[...]`` is not a substitute, because any module holding a reference to
the old object keeps it alive.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parents[2] / "lib"


@pytest.fixture
def broken_validator_tree(tmp_path: Path) -> Path:
    """sys.path entry whose ``eb_verify.plugins`` registry raises on import.

    Breaking a validator is what actually kills the registry: the 9 non-fact_triples
    validators are imported unguarded by ``plugins/__init__``.

    The whole tree is copied because the break must live inside the package:
    sys.path cannot shadow a submodule of ``eb_verify`` without shadowing
    ``eb_verify`` itself.
    """
    shadow = tmp_path / "broken_tree"
    shutil.copytree(
        LIB / "eb_verify",
        shadow / "eb_verify",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    # The missing dep must not be spelled with an ``eb_verify`` prefix: scorer_guard
    # greps stderr for "No module named 'eb_verify", so an eb_verify_* dep matches that
    # signature by accident and any probe asking "is this booked as infra?" answers yes
    # without the code under test doing anything.
    with (shadow / "eb_verify" / "plugins" / "call_graph.py").open("a") as fh:
        fh.write("\nimport simulated_absent_thirdparty_dep  # noqa: F401\n")
    return shadow


# Refuse to import the heavy stack, the way a minimal task sandbox does: lib's
# pyproject declares only jsonschema, so numpy-less is the canonical install.
BLOCK_HEAVY_DEPS = """
    import sys

    BLOCKED = ("numpy", "sklearn", "scipy")

    class _Blocker:
        def find_spec(self, name, path=None, target=None):
            if name.split(".")[0] in BLOCKED:
                raise ImportError(f"No module named {name!r} (numpy-less sandbox)")
            return None

    sys.meta_path.insert(0, _Blocker())
    for _m in [m for m in sys.modules if m.split(".")[0] in BLOCKED]:
        del sys.modules[_m]
"""


def run_in_fresh_interpreter(
    body: str,
    *,
    block_deps: bool,
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
