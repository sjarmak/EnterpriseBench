"""A planted ``/workspace/eb_verify`` must not shadow the real scorer.

Checkpoint scripts exec ``python3 -m eb_verify.plugins.…`` with ``cwd`` set to the
agent-writable workspace (``CheckpointRunner.run_checkpoint``). Python's ``-m`` puts
``cwd`` at ``sys.path[0]`` — ahead of the absolute ``_LIB_DIR`` that ``checkpoint_env``
prepends to ``PYTHONPATH``. So an agent that writes
``/workspace/eb_verify/plugins/file_extraction.py`` would shadow the shipped scorer and
mint its own ``{"score": 1.0}`` for a checkpoint it never solved (bead 5cfxa).

``checkpoint_env`` closes this by exporting ``PYTHONSAFEPATH=1`` (py>=3.11 drops the
cwd / script-dir entry from ``sys.path``). These vectors drive the real scorer through
the runner's own ``checkpoint_env`` so a change that dropped the flag surfaces as the
forgeable verdict it would be in a real run — and each one carries a non-vacuity twin
that removes the flag and asserts the planted module DOES win, so a test that passed
because the plant was never on the path cannot pass silently.

Scope: the guard here is the ``PYTHONSAFEPATH`` flag, which no-ops below py3.11. The
suite runs on whatever interpreter invokes it (CI is 3.12, the sandbox base is 3.11),
so it pins the shipped behaviour on supported hosts; a version-independent cwd control
for pre-3.11 hosts is tracked as follow-up (bead 5cfxa notes).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from eb_verify.runner import _LIB_DIR, checkpoint_env

MODULE = "eb_verify.plugins.file_extraction"
PWNED = "PWNED-agent-minted-verdict"


def _plant_shadow_workspace(tmp_path: Path) -> Path:
    """A workspace holding a hostile ``eb_verify`` package the agent could write.

    The planted scorer ignores its arguments and prints a full-marks verdict, exactly
    the forgery the real scorer must win over.
    """
    ws = tmp_path / "ws"
    plugins = ws / "eb_verify" / "plugins"
    plugins.mkdir(parents=True)
    (ws / "eb_verify" / "__init__.py").write_text("")
    (plugins / "__init__.py").write_text("")
    (plugins / "file_extraction.py").write_text(
        "import json\n"
        f'print(json.dumps({{"score": 1.0, "passed": True, "detail": "{PWNED}"}}))\n'
    )
    return ws


def _run_module(ws: Path, env: dict[str, str]) -> str:
    """``python -m eb_verify.plugins.file_extraction`` with ``cwd=ws``, as the runner does."""
    return subprocess.run(
        [sys.executable, "-m", MODULE],
        capture_output=True,
        text=True,
        cwd=str(ws),
        env=env,
        timeout=30,
    ).stdout


def test_checkpoint_env_sets_pythonsafepath(tmp_path):
    """Direct guard on the export, not one riding on an import resolving a certain way.

    Mirrors ``test_checkpoint_env_prepends_the_lib_dir_to_pythonpath``: asserts the built
    env dict itself, so the flag is guarded regardless of how ``eb_verify`` is installed
    or which Python runs the suite.
    """
    env = checkpoint_env(tmp_path / "ws", tmp_path / "task", "probe")
    assert env.get("PYTHONSAFEPATH") == "1", (
        "checkpoint_env must export PYTHONSAFEPATH=1 so a planted workspace eb_verify "
        f"cannot shadow the real scorer via cwd=sys.path[0]; got {env.get('PYTHONSAFEPATH')!r}"
    )


def test_planted_workspace_scorer_does_not_win(tmp_path):
    """The shipped scorer runs even when a hostile ``eb_verify`` sits in ``cwd``.

    Under ``checkpoint_env`` the real scorer answers (a VERIFIER_INFRA_ERROR here, since
    no ``--keys``/ground truth are passed) and the planted full-marks verdict never
    surfaces.
    """
    ws = _plant_shadow_workspace(tmp_path)
    env = checkpoint_env(ws, tmp_path / "task", "shadow-probe")
    out = _run_module(ws, env)

    assert PWNED not in out, (
        "a planted /workspace/eb_verify shadowed the real scorer — checkpoint verdicts "
        f"are agent-forgeable. stdout: {out!r}"
    )
    verdict = json.loads(out)
    assert verdict["score"] != 1.0, "planted scorer minted a 1.0 through the shadow"


def test_the_plant_actually_shadows_without_the_flag(tmp_path):
    """Non-vacuity twin: with PYTHONSAFEPATH removed, the plant DOES win.

    Proves the previous vector passes because the flag blocks the shadow, not because the
    planted module was never importable from ``cwd`` in the first place. If this ever
    stopped shadowing, ``test_planted_workspace_scorer_does_not_win`` would be green for
    the wrong reason.
    """
    ws = _plant_shadow_workspace(tmp_path)
    env = checkpoint_env(ws, tmp_path / "task", "shadow-probe")
    env.pop("PYTHONSAFEPATH", None)
    out = _run_module(ws, env)

    assert PWNED in out, (
        "the planted eb_verify did not shadow the real scorer even without "
        f"PYTHONSAFEPATH — the guard test would pass vacuously. stdout: {out!r}"
    )


def test_lib_dir_is_not_the_planted_workspace(tmp_path):
    """Guard-rail: the real scorer this suite defends lives outside any workspace."""
    ws = _plant_shadow_workspace(tmp_path)
    assert _LIB_DIR not in ws.parents and _LIB_DIR != ws
