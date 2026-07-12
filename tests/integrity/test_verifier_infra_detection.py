"""A verifier that never ran must never be scored — end-to-end (bead glka.2).

These vectors exec the REAL ``scripts/sandbox/test_runner.sh`` with the python3
interpreter genuinely absent from PATH, then route its output through the real
scorer trust boundary. Nothing here is synthetic: the same shell that runs in
the container produces the JSON that the same guard parses.

Two never-ran variants are proven, both of which used to land as a scored 0.0
that was indistinguishable from a genuine wrong answer:

* LOUD   — a bare ``python3`` under ``set -euo pipefail`` exits 127.
* SILENT — ``if python3 ... 2>/dev/null`` swallows the failure, so the verifier
  exits 0 and prints a well-formed ``{"score": 0.0}``. No exit code, no score,
  and no detail string distinguishes it from a real failure; only bash's
  command_not_found_handle side channel can see it.

The genuine-score controls are the point of the exercise: a wrong answer must
still be a 0.0 and a correct one still a 1.0, or the fix has merely traded a
false-zero problem for a false-infra one.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "lib"))

from eb_verify.scorer_guard import InfraError, guard_verifier_output  # noqa: E402

TEST_RUNNER = REPO_ROOT / "scripts" / "sandbox" / "test_runner.sh"

# Everything test_runner.sh legitimately needs — deliberately WITHOUT python3.
_REQUIRED_TOOLS = (
    "bash", "sed", "tr", "awk", "grep", "cat", "mktemp",
    "date", "basename", "rm", "timeout", "dirname", "env",
)

# --- the two never-ran variants, verbatim in shape from the real check scripts --

LOUD_MISSING_INTERPRETER = """\
#!/usr/bin/env bash
set -euo pipefail
python3 -c 'import json; print(json.dumps({"score": 1.0, "passed": True}))'
"""

SILENT_SWALLOWED_INTERPRETER = """\
#!/usr/bin/env bash
set -euo pipefail
if python3 -c "import sys; sys.exit(0)" 2>/dev/null; then
  printf '{"score": 1.0, "passed": true, "reason": "config consistent"}\\n'
else
  printf '{"score": 0.0, "passed": false, "reason": "config inconsistent"}\\n'
fi
exit 0
"""

GENUINE_WRONG_ANSWER = """\
#!/usr/bin/env bash
set -euo pipefail
printf '{"score": 0.0, "passed": false, "detail": "answer did not match ground truth"}\\n'
"""

GENUINE_PASS = """\
#!/usr/bin/env bash
set -euo pipefail
printf '{"score": 1.0, "passed": true, "detail": "all assertions held"}\\n'
"""


@pytest.fixture
def sanitized_path(tmp_path_factory) -> str:
    """A PATH with real coreutils but no python3 — a minimal image with no
    interpreter, which is exactly the condition the bead is about."""
    bin_dir = tmp_path_factory.mktemp("bin")
    for tool in _REQUIRED_TOOLS:
        resolved = shutil.which(tool)
        if resolved:
            (bin_dir / tool).symlink_to(resolved)
    assert shutil.which("python3", path=str(bin_dir)) is None, "python3 must be absent"
    return str(bin_dir)


def run_test_runner(workspace: Path, verifiers: dict[str, str], path: str) -> dict:
    """Exec the real test_runner.sh over ``verifiers`` and parse its JSON."""
    vdir = workspace / ".verifiers"
    vdir.mkdir(parents=True, exist_ok=True)
    (workspace / "repo-a" / ".git").mkdir(parents=True, exist_ok=True)

    for name, body in verifiers.items():
        script = vdir / f"{name}.sh"
        script.write_text(body)
        script.chmod(0o755)

    proc = subprocess.run(
        ["bash", str(TEST_RUNNER)],
        capture_output=True,
        text=True,
        env={"WORKSPACE": str(workspace), "PATH": path},
    )
    return json.loads(proc.stdout)


def checkpoint(result: dict, name: str) -> dict:
    return next(cp for cp in result["checkpoints"] if cp["name"] == name)


class TestNeverRanVerifierIsNotScored:
    def test_loud_missing_interpreter_is_not_attested(
        self, tmp_path: Path, sanitized_path: str
    ) -> None:
        """exit 127: the verifier died before reaching a verdict."""
        result = run_test_runner(
            tmp_path, {"loud": LOUD_MISSING_INTERPRETER}, sanitized_path
        )
        cp = checkpoint(result, "loud")
        assert cp["verifier_ran"] is False
        assert "python3" in cp["detail"]

    def test_silent_swallowed_interpreter_is_not_attested(
        self, tmp_path: Path, sanitized_path: str
    ) -> None:
        """The crux of the bead. The verifier exits 0 and prints a well-formed
        0.0, so exit code, score, and detail are all indistinguishable from a
        genuine wrong answer. Only the side channel sees the missing python3."""
        result = run_test_runner(
            tmp_path, {"silent": SILENT_SWALLOWED_INTERPRETER}, sanitized_path
        )
        cp = checkpoint(result, "silent")
        assert cp["exit_code"] == 0, "precondition: the failure IS swallowed"
        assert cp["verifier_ran"] is False, "a swallowed missing interpreter must still surface"
        assert "python3" in cp["detail"]

    @pytest.mark.parametrize(
        "name,body",
        [("loud", LOUD_MISSING_INTERPRETER), ("silent", SILENT_SWALLOWED_INTERPRETER)],
    )
    def test_never_ran_routes_to_infra_error_not_zero(
        self, tmp_path: Path, sanitized_path: str, name: str, body: str
    ) -> None:
        """Acceptance: a check script that shells a missing binary yields
        verifier_infra_error (the re-run channel), never a task_score of 0.0."""
        result = run_test_runner(tmp_path, {name: body}, sanitized_path)
        guarded = guard_verifier_output(json.dumps(result), returncode=1)
        assert isinstance(guarded, InfraError), f"{name} variant must not be scored"
        assert guarded.reason == "verifier_did_not_run"

    def test_no_verdict_is_never_fabricated_into_a_pass(
        self, tmp_path: Path, sanitized_path: str
    ) -> None:
        """Over-credit direction: a verifier that exits 0 printing NOTHING used
        to be fabricated into a free 1.0. Absence of a verdict is not a pass."""
        result = run_test_runner(
            tmp_path, {"silent_ok": "#!/usr/bin/env bash\nexit 0\n"}, sanitized_path
        )
        cp = checkpoint(result, "silent_ok")
        assert cp["verifier_ran"] is False
        assert cp["score"] == 0.0, "an empty verifier must never be credited a pass"
        assert isinstance(guard_verifier_output(json.dumps(result), returncode=0), InfraError)


class TestGenuineScoresSurvive:
    """The fix must not trade false zeros for false infra errors."""

    def test_genuine_wrong_answer_stays_a_scored_zero(
        self, tmp_path: Path, sanitized_path: str
    ) -> None:
        result = run_test_runner(
            tmp_path, {"wrong": GENUINE_WRONG_ANSWER}, sanitized_path
        )
        cp = checkpoint(result, "wrong")
        assert cp["verifier_ran"] is True
        assert cp["score"] == 0.0

        guarded = guard_verifier_output(json.dumps(result), returncode=1)
        assert isinstance(guarded, dict), "a real wrong answer is a score, not an infra error"
        assert guarded["task_score"] == 0.0

    def test_genuine_pass_stays_a_scored_one(
        self, tmp_path: Path, sanitized_path: str
    ) -> None:
        result = run_test_runner(tmp_path, {"pass": GENUINE_PASS}, sanitized_path)
        cp = checkpoint(result, "pass")
        assert cp["verifier_ran"] is True
        assert cp["score"] == 1.0

        guarded = guard_verifier_output(json.dumps(result), returncode=0)
        assert isinstance(guarded, dict)
        assert guarded["task_score"] == 1.0

    def test_one_broken_verifier_does_not_let_the_others_be_scored(
        self, tmp_path: Path, sanitized_path: str
    ) -> None:
        """A mixed run is an infra error for the WHOLE task: a task_score built
        from a partially-run verifier set is not a measurement of the agent."""
        result = run_test_runner(
            tmp_path,
            {
                "pass": GENUINE_PASS,
                "wrong": GENUINE_WRONG_ANSWER,
                "silent": SILENT_SWALLOWED_INTERPRETER,
            },
            sanitized_path,
        )
        assert checkpoint(result, "pass")["verifier_ran"] is True
        assert checkpoint(result, "wrong")["verifier_ran"] is True
        assert checkpoint(result, "silent")["verifier_ran"] is False

        guarded = guard_verifier_output(json.dumps(result), returncode=1)
        assert isinstance(guarded, InfraError)


def test_attestation_cannot_be_forged_by_a_check_script(
    tmp_path: Path, sanitized_path: str
) -> None:
    """.verifiers/ is agent-writable, so a check script may print whatever it
    likes — including a perfect score and a forged attestation. The attestation
    stamped into the checkpoint must be the RUNNER's own observation, never a
    value echoed back from the script's stdout.
    """
    forger = """\
#!/usr/bin/env bash
if python3 -c "pass" 2>/dev/null; then :; fi
printf '{"score": 1.0, "passed": true, "verifier_ran": true, "detail": "legit"}\\n'
exit 0
"""
    result = run_test_runner(tmp_path, {"forger": forger}, sanitized_path)
    cp = checkpoint(result, "forger")
    assert cp["verifier_ran"] is False, "a script must not be able to attest for itself"
    assert cp["score"] == 0.0, "the score printed alongside a forged attestation is discarded"
    assert "python3" in cp["detail"]
    assert isinstance(guard_verifier_output(json.dumps(result), returncode=0), InfraError)


def test_handler_does_not_fire_for_command_v_probes(
    tmp_path: Path, sanitized_path: str
) -> None:
    """False-positive guard for the side channel.

    The real config-drift scripts probe optional tooling with `command -v helm`
    and fall back when it is absent. `command -v` is a bash builtin, so it must
    NOT trip command_not_found_handle — otherwise every such script would become
    a spurious infra error. This is the only tool-probe idiom in the corpus.
    """
    probe = """\
#!/usr/bin/env bash
set -euo pipefail
if command -v helm &>/dev/null; then
  printf '{"score": 1.0, "passed": true, "detail": "helm present"}\\n'
else
  printf '{"score": 1.0, "passed": true, "detail": "helm absent, fell back"}\\n'
fi
"""
    result = run_test_runner(tmp_path, {"probe": probe}, sanitized_path)
    cp = checkpoint(result, "probe")
    assert cp["verifier_ran"] is True, "command -v is a builtin and must not trip the handler"
    assert cp["score"] == 1.0
    assert isinstance(guard_verifier_output(json.dumps(result), returncode=0), dict)
