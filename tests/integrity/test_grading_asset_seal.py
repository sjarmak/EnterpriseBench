"""Grading-asset trust boundary — the agent under test must not own the grader.

Before this seal, setup_container and _install_claude_cli both chowned
/workspace/.verifiers, /workspace/.task (ground_truth.json) and
/workspace/.eb_verify to the agent user, and the verifiers then ran AS that
same user with cwd=/workspace. So the party being graded could overwrite a
check with a forged verdict, read the answer key, or sabotage the harness
import for a free re-run (beads EnterpriseBench-8krz5, -g5k5s).

These vectors pin the boundary: grading assets are root-owned and
agent-unreadable, scoring executes as root from a root-owned cwd, and a broken
seal is reported as an ``integrity_violation`` — score 0.0, never routed to the
``verifier_infra_error`` re-run channel, so tampering is never a mulligan.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from orchestration.run_task import (  # noqa: E402
    GRADING_PATHS,
    SCORING_WORKDIR,
    WORKSPACE_DIR,
    _assert_grading_assets_sealed,
    _run_scoring,
    _seal_grading_assets,
)


def _is_parent_check(cmd: list[str]) -> bool:
    """The /workspace ownership+sticky probe (vs the grading-asset find)."""
    return len(cmd) > 2 and "maxdepth" in cmd[2]


def _ok(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=""
    )


def _fail(stderr: str = "boom", returncode: int = 1) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout="", stderr=stderr
    )


class TestGradingPathsConstant:
    def test_covers_every_grading_asset(self) -> None:
        assert set(GRADING_PATHS) == {
            "/workspace/.verifiers",
            "/workspace/.task",
            "/workspace/.eb_verify",
            "/workspace/test.sh",
        }

    def test_instruction_md_is_not_a_grading_asset(self) -> None:
        """instruction.md must stay agent-readable — the s58f readability gate
        depends on it, and sealing it would reintroduce fake-0 no-op runs."""
        assert "/workspace/instruction.md" not in GRADING_PATHS


class TestSetupChownSite:
    """SITE 1 — setup_container must not hand the grader to the agent."""

    def test_setup_chowns_instruction_but_no_grading_asset(self) -> None:
        from orchestration import run_task as rt

        captured: list[list[str]] = []

        with patch.object(rt, "_chown_to_agent") as chown:
            with patch.object(rt, "_docker_exec", return_value=_ok()), patch.object(
                rt, "_docker_cp"
            ):
                rt._setup_container("cid", Path("/nonexistent-task"), {})
            for call in chown.call_args_list:
                captured.append(call.args[1])

        assert captured, "_setup_container never called _chown_to_agent"
        chowned = [p for paths in captured for p in paths]
        assert "/workspace/instruction.md" in chowned
        for grading_path in GRADING_PATHS:
            assert grading_path not in chowned, (
                f"setup_container chowns {grading_path} to the agent — the agent "
                "under test would own its own grader"
            )


class TestInstallClaudeCliChownSite:
    """SITE 2 — _install_claude_cli re-granted .task/.verifiers unconditionally.

    A fix that patches only SITE 1 is silently defeated here.
    """

    def test_shell_command_touches_no_grading_asset(self) -> None:
        from orchestration import run_task as rt

        shell_cmds: list[str] = []

        def fake_exec(container_id, cmd, **kwargs):
            if cmd[:2] == ["bash", "-c"]:
                shell_cmds.append(cmd[2])
            return _ok(stdout="1.0.0")

        with patch.object(rt, "_docker_exec", side_effect=fake_exec):
            assert rt._install_claude_cli("cid") is True

        joined = "\n".join(shell_cmds)
        assert "/workspace/.task" not in joined
        assert "/workspace/.verifiers" not in joined
        assert "/workspace/agent_output" in joined, "agent output dir must stay agent-owned"
        assert "/home/agent" in joined


class TestSealGradingAssets:
    def test_seal_runs_as_root_and_strips_agent_access(self) -> None:
        from orchestration import run_task as rt

        with patch.object(rt, "_docker_exec", return_value=_ok()) as exec_:
            _seal_grading_assets("cid")

        kwargs = exec_.call_args.kwargs
        assert kwargs.get("user") == "root"
        script = exec_.call_args.args[1][2]
        assert "chown -R root:root" in script
        assert "go-rwx" in script
        for grading_path in GRADING_PATHS:
            assert grading_path in script
        assert SCORING_WORKDIR in script, "root-owned scoring cwd must be created"
        # The parent must be taken back from the agent and made sticky, or the
        # sealed entries can simply be renamed/unlinked out of it.
        assert f"chown root:root {WORKSPACE_DIR}" in script
        assert f"chmod 1777 {WORKSPACE_DIR}" in script

    def test_seal_failure_raises_loud(self) -> None:
        """An unsealed run is unscoreable — never silently continue (s58f: a
        masked chown failure is what produced fake-0 no-op runs)."""
        from orchestration import run_task as rt

        with patch.object(rt, "_docker_exec", return_value=_fail("chown: denied")):
            with pytest.raises(RuntimeError, match="seal"):
                _seal_grading_assets("cid")


class TestAssertGradingAssetsSealed:
    def test_clean_seal_passes(self) -> None:
        from orchestration import run_task as rt

        def fake_exec(container_id, cmd, **kwargs):
            # find reports nothing; agent cannot read ground truth
            if kwargs.get("user") == "agent":
                return _fail(returncode=1)
            return _ok(stdout="")

        with patch.object(rt, "_docker_exec", side_effect=fake_exec):
            ok, err = _assert_grading_assets_sealed("cid")

        assert ok is True
        assert err == ""

    def test_agent_owned_grading_file_is_a_breach(self) -> None:
        from orchestration import run_task as rt

        def fake_exec(container_id, cmd, **kwargs):
            if kwargs.get("user") == "agent":
                return _fail(returncode=1)
            if _is_parent_check(cmd):
                return _ok(stdout="")
            return _ok(stdout="/workspace/.verifiers/check_1.sh\n")

        with patch.object(rt, "_docker_exec", side_effect=fake_exec):
            ok, err = _assert_grading_assets_sealed("cid")

        assert ok is False
        assert "check_1.sh" in err

    def test_agent_owned_workspace_is_a_breach(self) -> None:
        """The parent governs unlink/rename. An agent-owned (or non-sticky)
        /workspace lets the agent move the sealed assets aside wholesale, no
        write to a sealed file required."""
        from orchestration import run_task as rt

        def fake_exec(container_id, cmd, **kwargs):
            if kwargs.get("user") == "agent":
                return _fail(returncode=1)
            if _is_parent_check(cmd):
                return _ok(stdout="/workspace\n")
            return _ok(stdout="")

        with patch.object(rt, "_docker_exec", side_effect=fake_exec):
            ok, err = _assert_grading_assets_sealed("cid")

        assert ok is False
        assert "unlink/rename" in err

    def test_deleted_grading_asset_is_a_breach_not_a_pass(self) -> None:
        """Fail CLOSED on absence. A deleted test.sh produces empty verifier
        output, which the scorer guard reads as verifier_infra_error — the
        re-run mulligan (g5k5s). An absent grader must never read as 'sealed'."""
        from orchestration import run_task as rt

        def fake_exec(container_id, cmd, **kwargs):
            if kwargs.get("user") == "agent":
                return _fail(returncode=1)
            if _is_parent_check(cmd):
                return _ok(stdout="")
            return _ok(stdout="MISSING:/workspace/test.sh\n")

        with patch.object(rt, "_docker_exec", side_effect=fake_exec):
            ok, err = _assert_grading_assets_sealed("cid")

        assert ok is False
        assert "test.sh" in err

    def test_absent_path_emits_missing_marker(self) -> None:
        """The probe must report absence, not silently skip it (`[ ! -e ]`)."""
        from orchestration import run_task as rt

        with patch.object(rt, "_docker_exec", return_value=_ok()) as exec_:
            _assert_grading_assets_sealed("cid")

        asset_probe = [
            c.args[1][2] for c in exec_.call_args_list
            if len(c.args) > 1 and isinstance(c.args[1], list)
            and len(c.args[1]) > 2 and "MISSING" in c.args[1][2]
        ]
        assert asset_probe, "seal probe never checks for a missing grading asset"
        assert '[ ! -e "$f" ]' in asset_probe[0]

    def test_agent_readable_ground_truth_is_a_breach(self) -> None:
        """Reading the answer key is as fatal as rewriting the checker."""
        from orchestration import run_task as rt

        def fake_exec(container_id, cmd, **kwargs):
            if kwargs.get("user") == "agent":
                return _ok(returncode=0)  # test -r succeeded
            return _ok(stdout="")  # parent + asset probes both clean

        with patch.object(rt, "_docker_exec", side_effect=fake_exec):
            ok, err = _assert_grading_assets_sealed("cid")

        assert ok is False
        assert "ground_truth" in err


class TestRunScoringUnderTheSeal:
    def test_scoring_execs_as_root_from_root_owned_cwd(self) -> None:
        """Ownership alone does not close the hole: 185 checks shell out to
        `python3 -c`, whose sys.path[0] is the cwd. Scoring from agent-owned
        /workspace lets a planted /workspace/json.py hijack the grader."""
        from orchestration import run_task as rt

        with patch.object(rt, "_assert_grading_assets_sealed", return_value=(True, "")):
            with patch.object(
                rt, "_docker_exec", return_value=_ok(stdout='{"task_score": 0.5}')
            ) as exec_:
                _run_scoring("cid")

        kwargs = exec_.call_args.kwargs
        assert kwargs.get("user") == "root"
        assert kwargs.get("workdir") == SCORING_WORKDIR
        assert "PYTHONSAFEPATH=1" in exec_.call_args.args[1][2]

    def test_breach_yields_integrity_violation_not_a_rerun(self) -> None:
        """The re-run channel keys off verifier_infra_error. Routing a breach
        there would make tampering a free mulligan (the g5k5s inversion)."""
        from orchestration import run_task as rt

        with patch.object(
            rt, "_assert_grading_assets_sealed", return_value=(False, "tampered")
        ):
            with patch.object(rt, "_docker_exec") as exec_:
                scores = _run_scoring("cid")

        exec_.assert_not_called(), "must not run a tampered verifier at all"
        assert scores["task_score"] == 0.0
        assert scores["all_passed"] is False
        assert "verifier_infra_error" not in scores
        assert scores["integrity_violation"]["reason"] == "grading_assets_tampered"


class TestScoringDoesNotBreakTheChecks:
    """The seal moves the scoring cwd and exec user. Both are load-bearing for
    the checks, and getting either wrong silently zeroes real checkpoints
    instead of crashing — the worst possible failure mode for a benchmark."""

    def test_runner_passes_workspace_as_first_arg(self) -> None:
        """11 checks resolve WORKSPACE="${1:-.}" and document "Receives
        workspace path as $1", but the runner never passed it — they worked only
        because the cwd happened to be /workspace. Off that cwd they would all
        score 0."""
        runner = (REPO_ROOT / "scripts/sandbox/test_runner.sh").read_text()
        assert 'bash "$verifier_path" "$WORKSPACE"' in runner
        assert 'timeout "$timeout_sec" bash "$verifier_path" "$WORKSPACE"' in runner

    def test_cwd_dependent_checks_still_resolve_off_the_scoring_cwd(
        self, tmp_path: Path
    ) -> None:
        """Drive a real cwd-dependent check from the new root-owned cwd."""
        check = (
            REPO_ROOT
            / "benchmarks/customer_escalation/chain-err-flask-import-001"
            / "checks/check_fix.sh"
        )
        if not check.exists():
            pytest.skip("task not present")

        workspace = tmp_path / "workspace"
        (workspace / "flask").mkdir(parents=True)
        # must clear the check's own >50-byte threshold to count as a summary
        (workspace / "flask" / "FIX_SUMMARY.md").write_text(
            "# Fix\n\nRoot cause: a circular import between flask/cli.py and "
            "flask/app.py. Broke the cycle by deferring the import.\n"
        )
        elsewhere = tmp_path / "eb_scoring"  # stands in for SCORING_WORKDIR
        elsewhere.mkdir()

        # cwd is NOT the workspace — exactly the post-seal scoring condition.
        out = subprocess.run(
            ["bash", str(check), str(workspace)],
            cwd=str(elsewhere),
            capture_output=True,
            text=True,
        )
        assert out.returncode == 0, out.stderr
        assert '"score": 0.0' not in out.stdout, (
            "check scored 0 off the scoring cwd — the workspace arg is not "
            f"being honoured: {out.stdout}"
        )

    def test_scoring_neutralizes_agent_controlled_git_config(self) -> None:
        """Scoring runs git as root inside agent-owned repos. safe.directory is
        required or `git diff` refuses (dubious ownership) and the check's
        `2>/dev/null || true` turns that into a false 'no code changes'. But
        trusting the repo must not let its config execute code as the scorer."""
        from orchestration import run_task as rt

        with patch.object(rt, "_assert_grading_assets_sealed", return_value=(True, "")):
            with patch.object(
                rt, "_docker_exec", return_value=_ok(stdout='{"task_score": 1.0}')
            ) as exec_:
                _run_scoring("cid")

        script = exec_.call_args.args[1][2]
        assert "safe.directory" in script
        # the two knobs git executes during `git diff`
        assert "core.fsmonitor" in script
        assert "core.hooksPath" in script
        assert "GIT_CONFIG_NOSYSTEM=1" in script


class TestIntegrityViolationRouting:
    def test_router_marks_run_invalid_and_never_succeeds(self) -> None:
        from orchestration import run_task as rt

        result = rt.TaskRunResult(task_id="t")
        rt._route_integrity_violation(
            result, {"integrity_violation": {"reason": "grading_assets_tampered"}}
        )

        assert result.failure_class == "integrity_violation"
        assert result.phase == "integrity_violation"
        assert result.status == rt.RUN_STATUS_INVALID
        assert result.success is False

    def test_clean_scores_leave_the_result_untouched(self) -> None:
        from orchestration import run_task as rt

        result = rt.TaskRunResult(task_id="t")
        rt._route_integrity_violation(result, {"task_score": 1.0})

        assert result.failure_class is None
        assert result.phase == ""


@pytest.mark.docker
class TestForgeAttackEndToEnd:
    """The empirical repro from the bead: chown -R agent + docker exec -u agent
    let the unprivileged user overwrite a verifier with a forged verdict."""

    def test_sealed_agent_cannot_forge_a_verdict_or_read_ground_truth(self) -> None:
        if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
            pytest.skip("docker daemon unavailable")

        # debian-based, matching every production base image in
        # dockerfile_generator (bash, GNU find, useradd).
        cid = subprocess.run(
            [
                "docker", "run", "-d", "--rm", "debian:bookworm-slim",
                "sleep", "300",
            ],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        try:
            subprocess.run(
                [
                    "docker", "exec", cid, "bash", "-c",
                    "useradd -m -s /bin/bash agent; "
                    # Production layout: dockerfile_generator hands /workspace
                    # to the agent. Sealing only the assets inside it is not
                    # enough — unlink/rename is governed by the PARENT's write
                    # bit — so the seal must take /workspace back. Reproducing
                    # this faithfully is what makes the vectors below real.
                    "mkdir -p /workspace && chown agent:agent /workspace; "
                    "mkdir -p /workspace/.verifiers /workspace/.task "
                    "/workspace/.eb_verify/eb_verify /workspace/agent_output; "
                    "chown agent:agent /workspace/agent_output; "
                    'echo \'{"score": 0.0}\' > /workspace/.verifiers/check_1.sh; '
                    'echo \'{"answer": "secret"}\' > /workspace/.task/ground_truth.json; '
                    "echo '# harness' > /workspace/.eb_verify/eb_verify/__init__.py; "
                    "touch /workspace/test.sh; "
                    # the pre-fix state: the agent owns the grader
                    "chown -R agent:agent /workspace/.verifiers /workspace/.task "
                    "/workspace/.eb_verify /workspace/test.sh",
                ],
                capture_output=True, check=True,
            )

            _seal_grading_assets(cid)

            forge = subprocess.run(
                [
                    "docker", "exec", "-u", "agent", cid, "sh", "-c",
                    'echo \'{"score": 1.0, "passed": true}\' > /workspace/.verifiers/check_1.sh',
                ],
                capture_output=True, text=True,
            )
            assert forge.returncode != 0, "agent forged a perfect verdict"

            leak = subprocess.run(
                ["docker", "exec", "-u", "agent", cid, "cat",
                 "/workspace/.task/ground_truth.json"],
                capture_output=True, text=True,
            )
            assert leak.returncode != 0, "agent read the answer key"
            assert "secret" not in leak.stdout

            # g5k5s: deleting or corrupting the harness the checks import must
            # not be reachable. Post-kyo34 a ModuleNotFoundError routes to
            # verifier_infra_error -> re-run, so a reachable sabotage would turn
            # a bad score into a free mulligan.
            #
            # The last four vectors are the PARENT-DIRECTORY bypass: they never
            # write to a sealed file at all, they unlink or rename it out of
            # /workspace and drop a forgery in its place. An earlier version of
            # this seal chowned the assets but left /workspace agent-owned, and
            # every one of these succeeded against it.
            for sabotage_cmd in (
                ["rm", "-rf", "/workspace/.eb_verify"],
                ["rm", "-f", "/workspace/.eb_verify/eb_verify/__init__.py"],
                ["sh", "-c", "echo raise ImportError > "
                             "/workspace/.eb_verify/eb_verify/__init__.py"],
                ["rm", "-rf", "/workspace/.verifiers"],
                ["rm", "-f", "/workspace/test.sh"],
                ["mv", "/workspace/test.sh", "/workspace/test.sh.bak"],
                ["mv", "/workspace/.verifiers", "/workspace/.verifiers.bak"],
                ["mv", "/workspace/.task", "/workspace/.task.bak"],
            ):
                sabotage = subprocess.run(
                    ["docker", "exec", "-u", "agent", cid] + sabotage_cmd,
                    capture_output=True,
                )
                assert sabotage.returncode != 0, (
                    f"agent sabotaged the harness via {' '.join(sabotage_cmd)} "
                    "— g5k5s mulligan is still reachable"
                )

            # test.sh survived intact — not unlinked and replaced by a forgery
            runner = subprocess.run(
                ["docker", "exec", cid, "cat", "/workspace/test.sh"],
                capture_output=True, text=True,
            )
            assert "FORGED" not in runner.stdout

            # ...and the agent can still do its actual job: write its answer,
            # drop a /workspace artifact, and clean up its own files.
            for legit_cmd in (
                ["sh", "-c", "echo '{}' > /workspace/agent_output/answer.json"],
                ["sh", "-c", "echo report > /workspace/BLAST_RADIUS.md"],
                ["rm", "-f", "/workspace/BLAST_RADIUS.md"],
            ):
                legit = subprocess.run(
                    ["docker", "exec", "-u", "agent", cid] + legit_cmd,
                    capture_output=True, text=True,
                )
                assert legit.returncode == 0, (
                    f"seal broke a legitimate agent action: {' '.join(legit_cmd)} "
                    f"-> {legit.stderr.strip()}"
                )

            # the harness is intact, so the checks still import it
            survives = subprocess.run(
                ["docker", "exec", cid, "cat",
                 "/workspace/.eb_verify/eb_verify/__init__.py"],
                capture_output=True, text=True,
            )
            assert survives.stdout.strip() == "# harness"

            ok, err = _assert_grading_assets_sealed(cid)
            assert ok is True, err

            # Fail CLOSED if a grading asset is gone. Even with /workspace
            # hardened this must hold: the assertion is the backstop, and a
            # backstop that reports "sealed" when the grader is absent would let
            # a deleted test.sh through as empty output -> verifier_infra_error
            # -> free re-run. Delete it as ROOT (the agent can no longer do so)
            # to prove the *detection* layer, not just the prevention layer.
            subprocess.run(
                ["docker", "exec", "-u", "root", cid, "rm", "-f",
                 "/workspace/test.sh"],
                capture_output=True, check=True,
            )
            ok, err = _assert_grading_assets_sealed(cid)
            assert ok is False, "a missing test.sh reported as sealed — fail-open"
            assert "test.sh" in err
        finally:
            subprocess.run(["docker", "kill", cid], capture_output=True)
