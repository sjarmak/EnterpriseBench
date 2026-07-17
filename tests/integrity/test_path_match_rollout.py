"""The path_match checks keep the harness PYTHONPATH authoritative.

Bead EnterpriseBench-u7d3f, the last two path_match-family sites of the shadow
defect EnterpriseBench-4du6t swept out of the topological_order family (itself
the twin of EnterpriseBench-njqo4). Each ``check_error_source.sh`` /
``check_root_cause.sh`` locates the repo lib/ by walking four levels up from its
``checks/`` dir and adding it to ``sys.path``. That walk is a GUESS: run the
check from anywhere but the repo tree and it resolves to whatever ``eb_verify``
happens to sit there, and ``sys.path.insert(0, ...)`` puts that ahead of the
PYTHONPATH the harness exports authoritatively (``eb_verify.runner.checkpoint_env``
on the host, ``/workspace/.eb_verify`` in the sandbox).

Found in the wild on ds-5090: a leftover ``/tmp/lib/eb_verify`` (a stale
pre-6py4v copy). A check copied under ``/tmp`` resolved its fallback to it and
at ``sys.path[0]`` that stale copy beat the real harness — the import failed or
imported a stale module, the check emitted VERIFIER_INFRA_ERROR, and the
scorer_guard routed every answer those tasks grade to a free re-run instead of a
score. That fails OPEN (silent over-credit), the s58f/hktt class.

The fix mirrors 4du6t: append the guessed dir (never insert(0)) so PYTHONPATH
stays authoritative, and guard on the MODULE actually imported, not just the
package dir — a ``-d "$LIB_DIR/eb_verify"`` check is what let a stale sibling
lacking the module through.

This suite is the path_match twin of ``test_topo_order_rollout.py``: both stale
variants (module absent / module booby-trapped), plus a non-vacuity twin proving
the harness genuinely detects shadowing by demonstrating the pre-fix pattern DOES
shadow.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BENCHMARKS = REPO_ROOT / "benchmarks"

# The path_match-family checks that use the lib/ fallback. A floor, not an
# equality: adding such a check must not force a test edit, but silently dropping
# below the family must fail rather than pass by matching nothing (the rot mode
# njqo4 documented).
MIN_CONVERTED = 2


def _discover() -> list[Path]:
    out = []
    for p in BENCHMARKS.glob("*/*/checks/*.sh"):
        if "_archived" in p.parts:
            continue
        text = p.read_text()
        if "SCRIPT_DIR/../../../../lib" in text and "eb_verify.plugins.path_match" in text:
            out.append(p)
    return sorted(out)


CONVERTED = _discover()


def _ids(p: Path) -> str:
    return str(p.relative_to(BENCHMARKS))


def test_rollout_covers_the_family() -> None:
    assert len(CONVERTED) >= MIN_CONVERTED, (
        f"only {len(CONVERTED)} path_match checks use the lib/ fallback, "
        f"expected >= {MIN_CONVERTED}. A check was renamed/retired or the scan "
        "stopped matching — either way the u7d3f rollout regressed."
    )


@pytest.mark.parametrize("script", CONVERTED, ids=_ids)
def test_appends_the_guessed_lib_never_inserts(script: Path) -> None:
    """insert(0) IS the defect: it beats the harness PYTHONPATH. Only append."""
    content = script.read_text()
    assert "sys.path.insert(0" not in content, (
        f"{script.relative_to(REPO_ROOT)} inserts the guessed lib at sys.path[0], "
        "shadowing the harness PYTHONPATH — use sys.path.append."
    )
    assert "sys.path.append(lib_dir)" in content


@pytest.mark.parametrize("script", CONVERTED, ids=_ids)
def test_guards_on_the_module_not_the_package_dir(script: Path) -> None:
    """A -d eb_verify check waves a stale package lacking the module through."""
    content = script.read_text()
    assert "eb_verify/plugins/path_match.py" in content, (
        f"{script.relative_to(REPO_ROOT)} does not guard LIB_DIR on the presence "
        "of the path_match module it imports."
    )


# --- Stale-sibling shadowing: the wild /tmp/lib bug, reproduced ---------------


def _plant(
    script: Path, tmp_path: Path, stale_module: str | None, *, content: str | None = None
) -> Path:
    """Copy *script* to a tree whose four-levels-up lib/ holds a stale eb_verify.

    Mirrors the real layout — benchmarks/<suite>/<task>/checks/ — so the script's
    own lib-dir fallback resolves to ``tmp_path/lib`` exactly as it resolves to
    the repo's lib/ in place. ``stale_module is None`` => package present but the
    path_match module absent; a string => module present and booby-trapped.
    ``content`` overrides the planted script body (used to plant the pre-fix
    pattern); defaults to *script* verbatim.
    """
    checks = tmp_path / "benchmarks" / "suite" / "task" / "checks"
    checks.mkdir(parents=True)
    plugins = tmp_path / "lib" / "eb_verify" / "plugins"
    plugins.mkdir(parents=True)
    (tmp_path / "lib" / "eb_verify" / "__init__.py").write_text("")
    (plugins / "__init__.py").write_text("")
    if stale_module is not None:
        (plugins / "path_match.py").write_text(stale_module)
    planted = checks / script.name
    planted.write_text(content if content is not None else script.read_text())
    return planted


def _run_planted(planted: Path, tmp_path: Path) -> subprocess.CompletedProcess:
    """Drive *planted* far enough to reach the eb_verify import.

    The check short-circuits before the import unless ground_truth.json (in
    TASK_DIR) and agent_output/answer.json (in WORKSPACE) both exist. Minimal
    valid contents let a healthy check run clean through to a real score, so any
    VERIFIER_INFRA_ERROR / crash the twin observes is the shadow, not the gate.
    """
    task_dir = planted.parent.parent
    (task_dir / "ground_truth.json").write_text(
        json.dumps({"required_files": [{"path": "app/main.py"}]})
    )
    workspace = tmp_path / "workspace"
    (workspace / "agent_output").mkdir(parents=True)
    (workspace / "agent_output" / "answer.json").write_text(
        json.dumps({"source_files": ["app/main.py"]})
    )
    return subprocess.run(
        ["bash", str(planted)],
        env={
            "PATH": "/usr/bin:/bin",
            "WORKSPACE": str(workspace),
            "TASK_DIR": str(task_dir),
            # What the harness really exports as the authoritative lib.
            "PYTHONPATH": str(REPO_ROOT / "lib"),
        },
        capture_output=True,
        text=True,
        timeout=60,
    )


def _shadow_reason(proc: subprocess.CompletedProcess) -> str | None:
    """None if the check produced a healthy verdict; else why it did not.

    A stale sibling defeats the harness in one of two ways: it crashes the check
    (no stdout, so the answer buys a free re-run) or it imports and the verdict
    carries VERIFIER_INFRA_ERROR. Either is a shadow; a clean verdict is None.
    """
    if not proc.stdout.strip():
        return f"crashed (rc={proc.returncode} stderr={proc.stderr!r}), no verdict"
    detail = json.loads(proc.stdout.strip().splitlines()[-1])["detail"]
    return detail if "VERIFIER_INFRA_ERROR" in detail else None


@pytest.mark.parametrize(
    "stale_module,label",
    [
        (None, "package present, module absent"),
        ("raise RuntimeError('stale lib won')", "module present but booby-trapped"),
    ],
)
@pytest.mark.parametrize("script", CONVERTED, ids=_ids)
def test_a_stale_sibling_lib_cannot_shadow_the_harness(
    script: Path, stale_module: str | None, label: str, tmp_path: Path
) -> None:
    """A stale eb_verify four levels up must not beat the harness PYTHONPATH."""
    planted = _plant(script, tmp_path, stale_module)
    proc = _run_planted(planted, tmp_path)
    reason = _shadow_reason(proc)
    assert reason is None, (
        f"a stale eb_verify ({label}) four levels up shadowed the real harness "
        f"for {script.relative_to(REPO_ROOT)}: {reason}"
    )


def test_the_prefix_pattern_would_shadow_non_vacuity(tmp_path: Path) -> None:
    """Prove the test bites: the pre-fix pattern DOES shadow the harness.

    Without this twin, the assertions above would pass just as well against a
    check that could never be shadowed for some unrelated reason. Reverting the
    two-line fix (insert(0) + drop the module guard) against a booby-trapped
    stale sibling must fail to produce a healthy verdict.
    """
    script = CONVERTED[0]
    content = script.read_text()
    vulnerable = content.replace(
        "sys.path.append(lib_dir)", "sys.path.insert(0, lib_dir)"
    ).replace(
        '[[ -f "$LIB_DIR/eb_verify/plugins/path_match.py" ]] || LIB_DIR=""\n',
        "",
    )
    assert vulnerable != content, "could not synthesise the pre-fix pattern"

    planted = _plant(
        script, tmp_path, "raise RuntimeError('stale lib won')", content=vulnerable
    )

    proc = _run_planted(planted, tmp_path)
    assert _shadow_reason(proc) is not None, (
        "the pre-fix insert(0) pattern did NOT shadow the booby-trapped stale "
        "sibling — the stale-sibling assertions above are vacuous."
    )
