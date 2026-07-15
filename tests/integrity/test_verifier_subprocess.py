"""The verdict-PRODUCING half of the scorer trust boundary (bead bbn22).

``guard_checkpoint_verdict`` owns PARSING a verdict and every runner routed
through it. PRODUCING one — resolve the path, run the subprocess, classify
escape / missing / timeout / exec-failure — was hand-rolled twice, and the two
copies had already diverged on every rung: milestone.py *raised* on a path
escape (crashing the chain mid-run) where runner.py returned an InfraError, and
caught only ``OSError`` where runner.py caught everything.

These tests exercise the lifted ``run_verifier_subprocess`` directly, so the
ladder is pinned once instead of twice. The per-runner wiring on top of it lives
in test_checkpoint_verdict.py (runner.py) and test_milestone_verdict.py
(milestone.py); the parse table it delegates to lives in
test_checkpoint_verdict.py.

The rule every rung serves: a verifier that did not reach a verdict has no
score, and the harness must say so — never a fabricated 1.0 (over-credit),
never a false 0.0 (blames the agent), never an exception (a harness bug
reported as a crash).
"""

from __future__ import annotations

import stat
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "lib"))

from eb_verify.scorer_guard import (  # noqa: E402
    NO_VERDICT_REASON,
    InfraError,
    run_verifier_subprocess,
)


def write_verifier(base: Path, name: str, body: str, executable: bool = True) -> str:
    """Write a stub verifier under ``base``; return its base-relative name."""
    path = base / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    if executable:
        path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return name


def run(base: Path, verifier: str, **kw):
    """Run ``verifier`` with the milestone convention (direct exec), unless
    overridden — the leaner of the two, so the argv plumbing stays visible."""
    kw.setdefault("cwd", base)
    kw.setdefault("timeout", 30)
    return run_verifier_subprocess(verifier, base_dir=base, checkpoint="cp1", **kw)


class TestTheLadder:
    """Each rung is an InfraError naming its own cause — never a score."""

    def test_path_escape_is_an_infra_error_not_an_exception(self, tmp_path):
        """milestone.py raised ValueError here and killed the chain."""
        result = run(tmp_path, "../../../etc/passwd")

        assert isinstance(result, InfraError)
        assert result.reason == NO_VERDICT_REASON
        assert result.context["cause"] == "path_escape"

    def test_a_symlink_out_of_the_base_dir_is_an_escape(self, tmp_path):
        """Containment is judged on the PHYSICAL target, not the link path.

        resolve() dereferences the symlink before either check runs, so the
        escape check sees the real outside path. Escaping via a symlink whose
        own name sits innocently inside base_dir therefore cannot work — which
        is the property worth pinning, since a link is the one way `verifier`
        can name an outside file without containing a single `..`.
        """
        outside = tmp_path.parent / "outside.sh"
        outside.write_text('#!/bin/sh\necho \'{"score": 1.0}\'\n')
        outside.chmod(0o755)
        base = tmp_path / "task"
        base.mkdir()
        (base / "link.sh").symlink_to(outside)

        result = run(base, "link.sh")

        assert isinstance(result, InfraError)
        assert result.context["cause"] == "path_escape"

    def test_the_base_dir_itself_is_not_a_verifier(self, tmp_path):
        """A directory cannot reach a verdict. Empty/'.' verifier paths resolve
        to base_dir, which exists — so containment must be strict."""
        result = run(tmp_path, ".")

        assert isinstance(result, InfraError)
        assert result.context["cause"] == "path_escape"

    def test_missing_verifier_is_infra(self, tmp_path):
        result = run(tmp_path, "does_not_exist.sh")

        assert isinstance(result, InfraError)
        assert result.context["cause"] == "missing_verifier"

    def test_timeout_is_infra_not_a_zero(self, tmp_path):
        v = write_verifier(tmp_path, "slow.sh", "#!/bin/sh\nsleep 5\n")

        result = run(tmp_path, v, timeout=1)

        assert isinstance(result, InfraError)
        assert result.context["cause"] == "verifier_timeout"

    def test_unexecutable_verifier_is_infra_not_a_crash(self, tmp_path):
        v = write_verifier(
            tmp_path, "noexec.sh", '#!/bin/sh\necho \'{"score": 1.0}\'\n',
            executable=False,
        )

        result = run(tmp_path, v)

        assert isinstance(result, InfraError)
        assert result.context["cause"] == "exec_error"

    def test_exec_failure_that_is_not_an_oserror_is_still_infra(self, tmp_path):
        """milestone.py caught OSError only. A bad env dict raises TypeError from
        inside subprocess — a harness bug, so it belongs in the re-run channel,
        not propagated as a crash."""
        v = write_verifier(tmp_path, "ok.sh", '#!/bin/sh\necho \'{"score": 1.0}\'\n')

        result = run(tmp_path, v, env={"BAD": None})  # type: ignore[dict-item]

        assert isinstance(result, InfraError)
        assert result.context["cause"] == "exec_error"

    def test_no_verdict_from_a_verifier_that_ran_is_infra(self, tmp_path):
        """The rung the guard owns — asserted here only as wiring."""
        v = write_verifier(tmp_path, "silent.sh", "#!/bin/sh\nexit 0\n")

        result = run(tmp_path, v)

        assert isinstance(result, InfraError)
        assert result.context["cause"] == "empty_output"


class TestAPathThatCannotBeResolvedIsInfra:
    """resolve() itself can fail, and it runs before every other rung.

    The ladder's first act is to resolve the verifier path — so a path that
    cannot be resolved at all fails *earlier* than the escape check that was
    supposed to be the first gate. Unguarded, resolve() raises straight out of
    run_verifier_subprocess and takes the whole checkpoint/milestone loop down
    mid-run, losing every other checkpoint's result. That is precisely the
    "harness bug reported as a crash, not a score" this module exists to
    prevent, and it contradicted the docstring's own claim that every rung is
    an InfraError.

    Old runner.py wrapped this step in `except ValueError`, so the null-byte
    case is a REGRESSION the lift introduced; the RuntimeError/OSError cases
    escaped both old runners and are pre-existing. All three arrive here now.
    """

    def test_symlink_loop_is_infra_not_a_crash(self, tmp_path):
        """The reachable one: resolve() raises RuntimeError on a symlink loop,
        which no old runner caught either."""
        (tmp_path / "a.sh").symlink_to(tmp_path / "b.sh")
        (tmp_path / "b.sh").symlink_to(tmp_path / "a.sh")

        result = run(tmp_path, "a.sh")

        assert isinstance(result, InfraError)
        assert result.reason == NO_VERDICT_REASON
        assert result.context["cause"] == "unresolvable_path"

    def test_null_byte_in_verifier_path_is_infra_not_a_crash(self, tmp_path):
        """resolve() raises ValueError('embedded null byte'). Old runner.py
        caught this and returned an InfraError; the lift dropped that guard."""
        result = run(tmp_path, "abc\x00def.sh")

        assert isinstance(result, InfraError)
        assert result.context["cause"] == "unresolvable_path"

    def test_unresolvable_base_dir_is_infra_not_a_crash(self, tmp_path):
        """base_dir is resolved too, and it is just as capable of failing."""
        (tmp_path / "a").symlink_to(tmp_path / "b")
        (tmp_path / "b").symlink_to(tmp_path / "a")

        result = run(tmp_path / "a", "check.sh")

        assert isinstance(result, InfraError)
        assert result.context["cause"] == "unresolvable_path"

    def test_overlong_name_is_infra_not_a_crash(self, tmp_path):
        """resolve() raises OSError(ENAMETOOLONG) — not a ValueError, so the
        narrow `except ValueError` the old runner used would not have held."""
        result = run(tmp_path, "z" * 5000 + ".sh")

        assert isinstance(result, InfraError)
        assert result.context["cause"] == "unresolvable_path"

    def test_the_verifier_is_named_in_the_evidence(self, tmp_path):
        """An operator triaging this needs the offending path, and it is the one
        thing the exception message may not carry."""
        result = run(tmp_path, "abc\x00def.sh")

        assert isinstance(result, InfraError)
        assert "abc" in str(result.context.get("verifier", ""))


class TestVerdictsPassThrough:
    def test_real_verdict_is_returned_whole(self, tmp_path):
        v = write_verifier(
            tmp_path, "good.sh", '#!/bin/sh\necho \'{"score": 0.75, "detail": "ok"}\'\n'
        )

        verdict = run(tmp_path, v)

        assert not isinstance(verdict, InfraError)
        assert verdict["score"] == 0.75
        assert verdict["passed"] is True

    def test_nested_verifier_inside_the_base_dir_is_allowed(self, tmp_path):
        """Both runners keep verifiers in a subdir (checks/); containment bounds
        the tree, it does not flatten it."""
        v = write_verifier(
            tmp_path, "checks/good.sh", '#!/bin/sh\necho \'{"score": 1.0}\'\n'
        )

        verdict = run(tmp_path, v)

        assert not isinstance(verdict, InfraError)
        assert verdict["score"] == 1.0


class TestCallersKeepTheirInvocationConvention:
    """The ladder is shared; how a verifier is *called* is not. Unifying that
    would have changed how the 3 real milestone verifiers are invoked, which is
    a behavior change bead bbn22 explicitly holds out of scope."""

    def test_argv_suffix_passes_the_workspace_as_argv_1(self, tmp_path):
        """milestone.py's convention: direct exec, workspace as argv[1]."""
        v = write_verifier(
            tmp_path, "echo_arg.sh", '#!/bin/sh\necho "{\\"score\\": 1.0, \\"message\\": \\"$1\\"}"\n'
        )

        verdict = run(tmp_path, v, argv_suffix=("/ws/path",))

        assert not isinstance(verdict, InfraError)
        assert verdict["message"] == "/ws/path"

    def test_argv_prefix_runs_the_verifier_under_an_interpreter(self, tmp_path):
        """runner.py's convention: `bash <script>`, so a non-executable check
        script still runs."""
        v = write_verifier(
            tmp_path, "noexec.sh", 'echo \'{"score": 1.0}\'\n', executable=False
        )

        verdict = run(tmp_path, v, argv_prefix=("bash",))

        assert not isinstance(verdict, InfraError)
        assert verdict["score"] == 1.0

    def test_env_contract_reaches_the_verifier(self, tmp_path):
        """runner.py's other half: WORKSPACE/TASK_DIR/TASK_ID by env."""
        v = write_verifier(
            tmp_path, "echo_env.sh", '#!/bin/sh\necho "{\\"score\\": 1.0, \\"message\\": \\"$TASK_ID\\"}"\n'
        )

        verdict = run(tmp_path, v, env={"TASK_ID": "eb-42", "PATH": "/usr/bin:/bin"})

        assert not isinstance(verdict, InfraError)
        assert verdict["message"] == "eb-42"

    def test_cwd_is_the_workspace_not_the_task_dir(self, tmp_path):
        """Both runners cd into the workspace: a verifier greps the agent's
        repos by relative path."""
        base = tmp_path / "task"
        base.mkdir()
        workspace = tmp_path / "ws"
        workspace.mkdir()
        v = write_verifier(
            base, "pwd.sh", '#!/bin/sh\necho "{\\"score\\": 1.0, \\"message\\": \\"$(pwd)\\"}"\n'
        )

        verdict = run(base, v, cwd=workspace)

        assert not isinstance(verdict, InfraError)
        assert verdict["message"] == str(workspace)


class TestStageRoutingIsPreserved:
    """`stage` names which scoring stage failed; the re-run channel triages on
    it, so the shared function must not flatten every caller into one."""

    def test_stage_is_carried_onto_the_infra_error(self, tmp_path):
        result = run(tmp_path, "missing.sh", stage="milestone")

        assert isinstance(result, InfraError)
        assert result.stage == "milestone"

    def test_stage_defaults_to_deterministic_scoring(self, tmp_path):
        result = run(tmp_path, "missing.sh")

        assert isinstance(result, InfraError)
        assert result.stage == "deterministic_scoring"

    def test_checkpoint_name_is_carried_onto_the_infra_error(self, tmp_path):
        result = run(tmp_path, "missing.sh")

        assert isinstance(result, InfraError)
        assert result.context["checkpoint"] == "cp1"
