"""Import-provenance guard for the first-party packages under ``lib/``.

A machine-global *editable* install (``__editable__.eb_verify-0.2.0.pth`` in
site-packages) can silently point ``import eb_verify`` at a DIFFERENT worktree's
``lib/`` — whichever tree happened to run ``pip install -e lib/`` last. When that
tree is stale it lacks modules added since (``scorer_guard``,
``plugins/file_extraction``), so a bare ``pytest`` on this box either errors at
collection or — worse, if the stale tree happens to carry the module — silently
exercises the WRONG code and reports green. That makes any pass/fail count a
measurement of someone else's snapshot, not this branch.

``tests/conftest.py`` defends against this by prepending THIS repo's ``lib/`` to
``sys.path`` before any test module is imported. These tests assert that defense
actually held: if either package resolves outside this repo root, fail loudly and
name the tree it leaked to, turning a silent wrong-tree import into a red test.

See EnterpriseBench-iqp6x.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

# tests/integrity/test_*.py -> parents[0]=integrity, [1]=tests, [2]=repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("module_name", ["eb_verify", "eb_metrics"])
def test_first_party_package_resolves_under_this_repo(module_name: str) -> None:
    module = importlib.import_module(module_name)
    assert module.__file__ is not None, (
        f"{module_name} has no __file__ (namespace or frozen module) — cannot "
        f"verify import provenance; see EnterpriseBench-iqp6x."
    )
    resolved = Path(module.__file__).resolve()

    assert resolved.is_relative_to(REPO_ROOT), (
        f"{module_name} imported from the WRONG tree: {resolved}\n"
        f"  expected it under this repo root: {REPO_ROOT}\n"
        f"A stale machine-global editable install (site-packages "
        f"__editable__*.pth) is shadowing the local package. Any pass/fail "
        f"count from this run measured that other tree, not this branch. "
        f"tests/conftest.py must prepend {REPO_ROOT / 'lib'} to sys.path "
        f"before the first import; see EnterpriseBench-iqp6x."
    )
