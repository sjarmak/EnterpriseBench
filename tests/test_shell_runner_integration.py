"""
Integration tests for shell-based test runners.

Exercises test_cross_repo_runner.sh end-to-end and validates test_runner.sh
JSON output against mock workspaces with various configurations.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

# conftest.py prepends this repo's lib/ to sys.path before any test module here
# is collected, so a plain import resolves — no local sys.path shim needed.
from eb_verify.scorer_guard import INFRA_SENTINEL


REPO_ROOT = Path(__file__).parent.parent
CROSS_REPO_RUNNER = REPO_ROOT / "tests" / "test_cross_repo_runner.sh"
TEST_RUNNER = REPO_ROOT / "scripts" / "sandbox" / "test_runner.sh"
# Independently needed to build PYTHONPATH for the child verifier process, which
# does NOT inherit the pytest process's sys.path.
REPO_LIB = REPO_ROOT / "lib"


# ---------------------------------------------------------------------------
# 1. Run test_cross_repo_runner.sh via subprocess
# ---------------------------------------------------------------------------


class TestCrossRepoRunnerScript:
    """Run the existing shell-based test suite and assert it exits cleanly."""

    def test_cross_repo_runner_exits_zero(self) -> None:
        assert CROSS_REPO_RUNNER.exists(), f"Missing {CROSS_REPO_RUNNER}"
        result = subprocess.run(
            ["bash", str(CROSS_REPO_RUNNER)],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, (
            f"test_cross_repo_runner.sh failed (exit {result.returncode}):\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


# ---------------------------------------------------------------------------
# 2. Run test_runner.sh against a mock workspace
# ---------------------------------------------------------------------------


def _make_patched_runner(tmp_path: Path, workspace: Path) -> Path:
    """A wrapper that runs the REAL test_runner.sh against a temp workspace.

    Points the runner at ``workspace`` through the WORKSPACE env var it honours,
    rather than string-patching a copy of its source. Source-patching silently
    no-ops the moment the matched line is reworded — the tests then score
    against the real ``/workspace`` and fail for reasons unrelated to the change
    that reworded it. This also means the tests exercise the runner that ships,
    not a mutated copy of it.
    """
    runner = tmp_path / "run_test_runner.sh"
    runner.write_text(
        "#!/usr/bin/env bash\n"
        f'export WORKSPACE="{workspace}"\n'
        f'exec bash "{TEST_RUNNER}" "$@"\n'
    )
    runner.chmod(runner.stat().st_mode | stat.S_IEXEC)
    return runner


def _build_workspace(
    workspace: Path,
    repos: list[str] | None = None,
    verifiers: dict[str, str] | None = None,
    meta: dict[str, str] | None = None,
    answer_json: str | None = None,
) -> None:
    """Build a mock workspace with fake repos and verifier scripts.

    ``answer_json``, if given, is written verbatim to
    ``agent_output/answer.json`` — the artifact test_runner.sh inspects to set
    AGENT_OUTPUT_INVALID.
    """
    if answer_json is not None:
        agent_output = workspace / "agent_output"
        agent_output.mkdir(exist_ok=True)
        (agent_output / "answer.json").write_text(answer_json)

    if repos:
        for repo in repos:
            git_dir = workspace / repo / ".git"
            git_dir.mkdir(parents=True, exist_ok=True)
        markers = workspace / ".markers"
        markers.mkdir(exist_ok=True)
        for repo in repos:
            (markers / f"{repo}.status").write_text("OK")

    if verifiers:
        verifier_dir = workspace / ".verifiers"
        verifier_dir.mkdir(exist_ok=True)
        for name, script in verifiers.items():
            path = verifier_dir / f"{name}.sh"
            path.write_text(script)
            path.chmod(path.stat().st_mode | stat.S_IEXEC)

    if meta:
        verifier_dir = workspace / ".verifiers"
        verifier_dir.mkdir(exist_ok=True)
        for name, content in meta.items():
            (verifier_dir / f"{name}.meta").write_text(content)


PASS_VERIFIER = """\
#!/usr/bin/env bash
echo '{"score": 1.0, "passed": true, "detail": "ok"}'
exit 0
"""

FAIL_VERIFIER = """\
#!/usr/bin/env bash
echo '{"score": 0.0, "passed": false, "detail": "nope"}'
exit 1
"""


class TestRunnerJsonOutput:
    """Run test_runner.sh against mock workspaces and validate JSON output."""

    def test_two_checkpoints_mixed(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        _build_workspace(
            workspace,
            repos=["alpha", "beta"],
            verifiers={"01-pass": PASS_VERIFIER, "02-fail": FAIL_VERIFIER},
            meta={"01-pass": "weight=0.4", "02-fail": "weight=0.6"},
        )
        runner = _make_patched_runner(tmp_path, workspace)

        result = subprocess.run(
            ["bash", str(runner)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0, "Should fail when not all checkpoints pass"

        data = json.loads(result.stdout)
        assert "task_score" in data
        assert "all_passed" in data
        assert "checkpoints_passed" in data
        assert "checkpoints_total" in data
        assert "checkpoints" in data
        assert "repos" in data

        assert data["all_passed"] is False
        assert data["checkpoints_passed"] == 1
        assert data["checkpoints_total"] == 2
        assert abs(data["task_score"] - 0.4) < 0.01
        # Note: test_runner.sh discover_repos uses mapfile + awk which may
        # serialize only the first element; assert at least one repo appears
        assert len(data["repos"]) >= 1
        assert "alpha" in data["repos"] or "beta" in data["repos"]

        assert len(data["checkpoints"]) == 2
        for cp in data["checkpoints"]:
            assert "name" in cp
            assert "weight" in cp
            assert "score" in cp
            assert "passed" in cp
            assert "duration_ms" in cp
            assert "exit_code" in cp

    def test_all_pass(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        _build_workspace(
            workspace,
            repos=["repo-a"],
            verifiers={"01-check": PASS_VERIFIER},
        )
        runner = _make_patched_runner(tmp_path, workspace)

        result = subprocess.run(
            ["bash", str(runner)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0

        data = json.loads(result.stdout)
        assert data["all_passed"] is True
        assert data["checkpoints_passed"] == 1
        assert data["task_score"] >= 1.0 - 0.01

    def test_single_checkpoint_mode(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        _build_workspace(
            workspace,
            repos=["repo-a"],
            verifiers={"01-check": PASS_VERIFIER},
        )
        runner = _make_patched_runner(tmp_path, workspace)

        result = subprocess.run(
            ["bash", str(runner), "01-check"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0

        data = json.loads(result.stdout)
        assert data["passed"] is True
        assert data["score"] == 1.0


# ---------------------------------------------------------------------------
# 3. Edge cases
# ---------------------------------------------------------------------------


class TestRunnerEdgeCases:
    """Edge cases: missing verifiers dir, single checkpoint, timeout."""

    def test_no_verifiers_dir(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        # No .verifiers/ directory at all
        runner = _make_patched_runner(tmp_path, workspace)

        result = subprocess.run(
            ["bash", str(runner)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0

        data = json.loads(result.stdout)
        assert data["all_passed"] is False

    def test_single_checkpoint_full_run(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        _build_workspace(
            workspace,
            repos=["solo"],
            verifiers={"01-only": PASS_VERIFIER},
        )
        runner = _make_patched_runner(tmp_path, workspace)

        result = subprocess.run(
            ["bash", str(runner)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0

        data = json.loads(result.stdout)
        assert data["checkpoints_total"] == 1
        assert data["checkpoints_passed"] == 1
        assert data["all_passed"] is True

    def test_verifier_timeout(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        slow_verifier = """\
#!/usr/bin/env bash
sleep 30
echo '{"score": 1.0, "passed": true, "detail": "too slow"}'
exit 0
"""
        _build_workspace(
            workspace,
            repos=["repo-a"],
            verifiers={"01-slow": slow_verifier},
            meta={"01-slow": "weight=1.0\ntimeout=2"},
        )
        runner = _make_patched_runner(tmp_path, workspace)

        result = subprocess.run(
            ["bash", str(runner)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0

        data = json.loads(result.stdout)
        assert data["all_passed"] is False
        # The checkpoint should report timeout
        assert len(data["checkpoints"]) == 1
        assert data["checkpoints"][0]["passed"] is False

    def test_invalid_checkpoint_name_rejected(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        _build_workspace(
            workspace,
            repos=["repo-a"],
            verifiers={"01-check": PASS_VERIFIER},
        )
        runner = _make_patched_runner(tmp_path, workspace)

        result = subprocess.run(
            ["bash", str(runner), "../etc/passwd"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0
        assert "Invalid checkpoint name" in result.stdout


# ---------------------------------------------------------------------------
# 4. Harness-death attribution (bead EnterpriseBench-w37sj)
# ---------------------------------------------------------------------------

# A check script reproducing the LIVE production harness-import death: the
# eb_verify package imports (PYTHONPATH points at the repo's lib/) but the
# `file_extraction` plugin submodule does not exist, so runpy emits the
# apostrophe-FREE "No module named eb_verify.plugins.file_extraction" on stderr,
# exits nonzero, and prints no JSON verdict. This is the exact signature the two
# active err-provenance tasks hit — the harness died, not the agent.
HARNESS_IMPORT_DEATH_VERIFIER = f"""\
#!/usr/bin/env bash
set -e
export PYTHONPATH="{REPO_LIB}"
python3 -m eb_verify.plugins.file_extraction "$1/agent_output/answer.json"
echo '{{"score": 1.0, "passed": true, "detail": "unreachable"}}'
"""

# A check script that dies on the agent's own malformed answer.json AFTER the
# harness imported cleanly — a genuine agent-artifact failure. Its stderr is a
# Python TypeError, never the eb_verify harness signature. This is the behaviour
# the fix must PRESERVE: scored 0.0 as agent performance, not routed to infra.
AGENT_ARTIFACT_DEATH_VERIFIER = """\
#!/usr/bin/env bash
set -e
python3 -c "import json, sys
with open(sys.argv[1]) as fh:
    print(json.load(fh)['expected_key'])" "$1/agent_output/answer.json"
echo '{"score": 1.0, "passed": true, "detail": "unreachable"}'
"""

# Not a JSON object, so test_runner.sh sets AGENT_OUTPUT_INVALID — the precondition
# that, before the fix, laundered the harness death into a scored 0.0.
MALFORMED_ANSWER = '["not", "an", "object"]'


class TestHarnessDeathAttribution:
    """A harness-import death must never be scored as agent performance, even
    when the agent's answer.json is ALSO malformed (bead w37sj)."""

    def test_harness_death_with_malformed_answer_routes_to_infra(
        self, tmp_path: Path
    ) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        _build_workspace(
            workspace,
            repos=["repo-a"],
            verifiers={"01-harness": HARNESS_IMPORT_DEATH_VERIFIER},
            answer_json=MALFORMED_ANSWER,
        )
        runner = _make_patched_runner(tmp_path, workspace)

        result = subprocess.run(
            ["bash", str(runner)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        data = json.loads(result.stdout)
        assert len(data["checkpoints"]) == 1
        cp = data["checkpoints"][0]
        # The harness died before it could judge anything — attribution is
        # infra, never the agent. Pre-fix this asserted verifier_ran=true + 0.0.
        assert cp["verifier_ran"] is False, (
            f"harness import death was laundered into agent performance: {cp}"
        )
        assert INFRA_SENTINEL in cp["detail"]

    def test_harness_death_single_checkpoint_mode_routes_to_infra(
        self, tmp_path: Path
    ) -> None:
        # Single-checkpoint mode emits the raw per-checkpoint verdict, whose only
        # downstream infra hook is the INFRA_SENTINEL detail signature — so the
        # new infra_detail must carry that prefix for this path too.
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        _build_workspace(
            workspace,
            repos=["repo-a"],
            verifiers={"01-harness": HARNESS_IMPORT_DEATH_VERIFIER},
            answer_json=MALFORMED_ANSWER,
        )
        runner = _make_patched_runner(tmp_path, workspace)

        result = subprocess.run(
            ["bash", str(runner), "01-harness"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        data = json.loads(result.stdout)
        assert data.get("verifier_ran") is False, (
            f"single-checkpoint harness death scored as agent performance: {data}"
        )
        assert INFRA_SENTINEL in data.get("detail", "")

    def test_genuine_agent_artifact_death_still_scored_zero(
        self, tmp_path: Path
    ) -> None:
        # The fix must be surgical: an answer.json that kills a check which
        # imported the harness cleanly is still the agent's 0.0, not infra.
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        _build_workspace(
            workspace,
            repos=["repo-a"],
            verifiers={"01-agent": AGENT_ARTIFACT_DEATH_VERIFIER},
            answer_json=MALFORMED_ANSWER,
        )
        runner = _make_patched_runner(tmp_path, workspace)

        result = subprocess.run(
            ["bash", str(runner)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        data = json.loads(result.stdout)
        cp = data["checkpoints"][0]
        assert cp["verifier_ran"] is True, (
            f"genuine agent-artifact failure misrouted to infra: {cp}"
        )
        assert cp["score"] == 0.0
        # Explicit: this path must NOT be routed to infra, so it must carry no
        # infra signature. Fails loudly if a future change couples the fields.
        assert INFRA_SENTINEL not in cp["detail"]


# ---------------------------------------------------------------------------
# 5. Transitive-dep harness death (bead EnterpriseBench-eth0x)
# ---------------------------------------------------------------------------

# w37sj closed the eb_verify-NAMESPACE death (the package/submodule is absent, so
# the module name after "No module named" IS eb_verify). This class covers the
# adjacent gap it left open: a harness death from a missing THIRD-PARTY
# dependency of a plugin. fact_triples.py does an unguarded top-level
# `from jsonschema import ...`, so with jsonschema absent the failure is
# "ModuleNotFoundError: No module named 'jsonschema'" — the eb_verify token
# appears only in the traceback File-frame path, never after "No module named".
# The name-only matcher missed it, and paired with a malformed answer.json the
# harness death was laundered into a scored agent 0.0 (the same family w37sj fixed).
#
# jsonschema is currently present (4.26.0), so these tests do NOT remove it.
# Instead each fixture reproduces the exact failure SHAPE with a synthetic
# package whose path carries the real "/eb_verify/" segment, run through a real
# `python3 -m` invocation so the traceback (caret lines and all) is genuine.


def _write_py(path: Path, body: str) -> None:
    """Write a module, creating its parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)


def _synthetic_eb_verify_plugin(root: Path, module_body: str) -> Path:
    """Build <root>/eb_verify/plugins/fact_triples.py with an eb_verify package
    chain, so its traceback frame path contains the anchored "/eb_verify/"
    segment exactly as the sealed sandbox copy (/workspace/.eb_verify/eb_verify/)
    and the editable install (lib/eb_verify/) both do. Returns ``root``."""
    _write_py(root / "eb_verify" / "__init__.py", "")
    _write_py(root / "eb_verify" / "plugins" / "__init__.py", "")
    _write_py(root / "eb_verify" / "plugins" / "fact_triples.py", module_body)
    return root


def _fact_triples_verifier(pythonpath: str) -> str:
    """A check that runs the fact_triples plugin under ``pythonpath``. ``set -e``
    aborts before the echo when the plugin import dies, so the trailing 1.0
    verdict is emitted only if the import unexpectedly SUCCEEDS — proving routing
    keys on the death, not on the mere absence of a printed verdict."""
    return (
        "#!/usr/bin/env bash\n"
        "set -e\n"
        f'export PYTHONPATH="{pythonpath}"\n'
        'python3 -m eb_verify.plugins.fact_triples "$1/agent_output/answer.json"\n'
        "echo '{\"score\": 1.0, \"passed\": true, \"detail\": \"unreachable\"}'\n"
    )


class TestTransitiveDepHarnessDeath:
    """A harness death from a MISSING TRANSITIVE DEPENDENCY of a plugin must route
    to infra, never launder into a scored agent 0.0 — even when answer.json is
    also malformed (bead EnterpriseBench-eth0x, follow-up to w37sj)."""

    def test_direct_missing_dep_routes_to_infra(self, tmp_path: Path) -> None:
        # The stated reproduction: a plugin's own top-level import of an absent
        # third-party name. The culprit frame is the eb_verify plugin itself, and
        # the missing module name is NOT eb_verify — so only the frame-provenance
        # rule (not the name grep) can catch it. RED before the fix: pre-fix the
        # matcher missed this and the malformed answer laundered it to 0.0.
        pkg = _synthetic_eb_verify_plugin(
            tmp_path / "harness_root",
            "from __absent_harness_dep__ import Thing\n",
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        _build_workspace(
            workspace,
            repos=["repo-a"],
            verifiers={"01-harness": _fact_triples_verifier(str(pkg))},
            answer_json=MALFORMED_ANSWER,
        )
        runner = _make_patched_runner(tmp_path, workspace)

        result = subprocess.run(
            ["bash", str(runner)], capture_output=True, text=True, timeout=30
        )

        data = json.loads(result.stdout)
        assert len(data["checkpoints"]) == 1
        cp = data["checkpoints"][0]
        assert cp["verifier_ran"] is False, (
            f"transitive-dep harness death laundered into agent performance: {cp}"
        )
        assert INFRA_SENTINEL in cp["detail"]

    def test_direct_missing_dep_single_checkpoint_mode(self, tmp_path: Path) -> None:
        # Single-checkpoint mode emits the raw per-checkpoint verdict, whose only
        # downstream infra hook is the INFRA_SENTINEL detail signature.
        pkg = _synthetic_eb_verify_plugin(
            tmp_path / "harness_root",
            "from __absent_harness_dep__ import Thing\n",
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        _build_workspace(
            workspace,
            repos=["repo-a"],
            verifiers={"01-harness": _fact_triples_verifier(str(pkg))},
            answer_json=MALFORMED_ANSWER,
        )
        runner = _make_patched_runner(tmp_path, workspace)

        result = subprocess.run(
            ["bash", str(runner), "01-harness"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        data = json.loads(result.stdout)
        assert data.get("verifier_ran") is False, (
            f"single-checkpoint transitive-dep death scored as agent: {data}"
        )
        assert INFRA_SENTINEL in data.get("detail", "")

    def test_dep_of_dep_missing_routes_to_infra(self, tmp_path: Path) -> None:
        # The transitive case the bead's title actually names: jsonschema is
        # PRESENT but one of ITS deps is absent, so the culprit frame is a
        # third-party file with NO eb_verify in its path. A deepest-frame rule
        # would miss this; scanning all frames (harness frame present, no subject
        # frame) catches it. This locks in the CONFIRMED-review robustness point.
        root = tmp_path / "harness_root"
        _synthetic_eb_verify_plugin(root, "import _harness_intermediate_dep\n")
        _write_py(
            root / "_harness_intermediate_dep" / "__init__.py",
            "import __absent_leaf_dep__\n",
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        _build_workspace(
            workspace,
            repos=["repo-a"],
            verifiers={"01-harness": _fact_triples_verifier(str(root))},
            answer_json=MALFORMED_ANSWER,
        )
        runner = _make_patched_runner(tmp_path, workspace)

        result = subprocess.run(
            ["bash", str(runner)], capture_output=True, text=True, timeout=30
        )

        data = json.loads(result.stdout)
        assert len(data["checkpoints"]) == 1
        cp = data["checkpoints"][0]
        assert cp["verifier_ran"] is False, (
            f"dep-of-dep harness death laundered into agent performance: {cp}"
        )
        assert INFRA_SENTINEL in cp["detail"]

    def test_subject_moduleerror_below_harness_frame_still_scored_zero(
        self, tmp_path: Path
    ) -> None:
        # The surgical guard: a harness plugin that imports SUBJECT code, and the
        # subject's own import fails. The traceback stacks an eb_verify frame ABOVE
        # a "/workspace/<repo>/" subject frame — the exact false-positive the "no
        # subject frame" clause exists to reject. This is the agent/task's own
        # ModuleNotFoundError and must stay scored 0.0, not routed to infra.
        pkg = _synthetic_eb_verify_plugin(
            tmp_path / "harness_root", "import subjectmod\n"
        )
        # Subject module lives under a "/workspace/<repo>/" path so its frame is
        # recognised as subject, not harness.
        subject_dir = tmp_path / "workspace" / "repo-a"
        _write_py(subject_dir / "subjectmod.py", "import __absent_subject_dep__\n")
        workspace = tmp_path / "workspace"
        workspace.mkdir(exist_ok=True)
        pythonpath = os.pathsep.join([str(pkg), str(subject_dir)])
        _build_workspace(
            workspace,
            repos=["repo-a"],
            verifiers={"01-agent": _fact_triples_verifier(pythonpath)},
            answer_json=MALFORMED_ANSWER,
        )
        runner = _make_patched_runner(tmp_path, workspace)

        result = subprocess.run(
            ["bash", str(runner)], capture_output=True, text=True, timeout=30
        )

        data = json.loads(result.stdout)
        assert len(data["checkpoints"]) == 1
        cp = data["checkpoints"][0]
        assert cp["verifier_ran"] is True, (
            f"subject-code ModuleNotFoundError misrouted to infra: {cp}"
        )
        assert cp["score"] == 0.0
        assert INFRA_SENTINEL not in cp["detail"]

    def test_stdout_frame_noise_does_not_suppress_harness_death(
        self, tmp_path: Path
    ) -> None:
        # A genuine harness import death (traceback on stderr) must still route to
        # infra when the verifier ALSO prints a subject-frame-shaped line to
        # STDOUT. The frame scan is stderr-only precisely so stdout noise —
        # verifier logging, or agent-echoed answer text — cannot set the subject
        # flag and launder a real harness death back into a scored 0.0.
        pkg = _synthetic_eb_verify_plugin(
            tmp_path / "harness_root",
            "from __absent_harness_dep__ import Thing\n",
        )
        verifier = (
            "#!/usr/bin/env bash\n"
            "set -e\n"
            f'export PYTHONPATH="{pkg}"\n'
            # A traceback-shaped line on STDOUT naming a /workspace subject path:
            # if the scan were not stderr-only this would set subject and suppress.
            "echo '  File \"/workspace/repo-a/notes.py\", line 1, in <module>'\n"
            'python3 -m eb_verify.plugins.fact_triples "$1/agent_output/answer.json"\n'
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        _build_workspace(
            workspace,
            repos=["repo-a"],
            verifiers={"01-harness": verifier},
            answer_json=MALFORMED_ANSWER,
        )
        runner = _make_patched_runner(tmp_path, workspace)

        result = subprocess.run(
            ["bash", str(runner)], capture_output=True, text=True, timeout=30
        )

        data = json.loads(result.stdout)
        assert len(data["checkpoints"]) == 1
        cp = data["checkpoints"][0]
        assert cp["verifier_ran"] is False, (
            f"stdout frame-noise suppressed a genuine harness death: {cp}"
        )
        assert INFRA_SENTINEL in cp["detail"]
