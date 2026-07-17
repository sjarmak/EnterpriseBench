"""file_extraction under-credit vectors.

The under-credit half of this corpus: a verifier that zeros a correct,
spec-compliant answer books a harness bug as an agent failure. Each vector
asserts the correct 1.0 against an answer that a buggy verifier scored 0.0.
Run as an un-skippable gate (CI), separately from the marker-filtered suite.

Every vector drives the *shipped* check scripts — discovered by running them and
watching for the scorer, then executed through the runner's own ``checkpoint_env``
— rather than restating their arguments here. An earlier draft restated the
scripts' ``--keys`` as a local constant, so it exercised the module's parsing
(never broken) instead of the key list (the actual bug), and stayed green when the
shipped list lost
``code_paths``/``citations``. So the key list appears nowhere below: drop a key from
a check script and these go red.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# The runner's own env builder, not a copy of it: a hand-rolled PYTHONPATH here
# would keep passing after the runner stopped exporting one. _LIB_DIR is the runner's
# own notion of where eb_verify lives — asserting against a copy of it would be the
# same drift this whole corpus exists to catch.
from eb_verify.runner import _LIB_DIR, checkpoint_env

# The scorer's OWN argument parser, so shipped_keys() reads --keys exactly as the
# scorer does — no second, drift-prone parser. HarnessError is what it raises on a
# malformed invocation.
from eb_verify.scorers.file_extraction import HarnessError, build_parser

REPO_ROOT = Path(__file__).resolve().parents[2]

# One spelling of the module name, shared by the prefilter and the shim below. Two
# copies that drift is the same class of bug this corpus exists to catch.
SCORER_MODULE = "eb_verify.scorers.file_extraction"

# (repo, path) pairs, as required_files entries really are: repo-prefixed paths, as
# both live ground truths spell them, because the scorer indexes a multi-repo
# workspace. The two files sit in different repos, so nothing here is ambiguous.
GT = [("httpx", "httpx/httpx/_config.py"), ("httpcore", "httpcore/httpcore/_client.py")]

# The shape run_task.py's mandatory output appendix dictates to every agent:
# "All file paths MUST be absolute and anchored at /workspace/<repo>/...".
ABSOLUTE = [f"/workspace/{path}" for _, path in GT]


def _stage_workspace(workdir: Path, answer: dict) -> tuple[Path, Path]:
    """Stage the workspace and task dir a shipped check script expects to find.

    ONE fixture for both the probe and the vectors, because most shipped check scripts
    open with a hardening preamble that refuses a missing ground_truth.json or
    answer.json and exits before scoring. A probe that staged less than the vectors do
    would read that early exit as "this script never calls the scorer" and silently drop
    a real caller from the corpus — the same false verdict this corpus exists to catch,
    aimed at itself.

    Insurance for the auto-adoption path, not for today: none of the three current
    callers guards its inputs, and all three are discovered with a bare workspace too
    (measured). It is the scripts bead rmz1x will point here that carry the preamble, and
    they would drop out silently on arrival. Staging now costs one fixture; finding out
    later costs a gate that shrank while green.
    """
    task_dir = workdir / "task"
    task_dir.mkdir(exist_ok=True)
    (task_dir / "ground_truth.json").write_text(
        json.dumps({"required_files": [{"path": path, "repo": repo} for repo, path in GT]})
    )

    workspace = workdir / "ws"
    (workspace / "agent_output").mkdir(parents=True, exist_ok=True)
    (workspace / "agent_output" / "answer.json").write_text(json.dumps(answer))
    return workspace, task_dir


# The probe answers in every shape at once. It only has to clear the bash-level guards
# and reach the scorer — the shim short-circuits before any real scoring — so breadth
# here buys immunity to a script that inspects the answer before invoking the scorer.
PROBE_ANSWER = {
    "source_files": ABSOLUTE,
    "files": ABSOLUTE,
    "code_paths": [{"path": path} for path in ABSOLUTE],
    "error_source": {"files": ABSOLUTE},
    "citations": [
        {"repo": repo, "file": path, "evidence_span": "x" * 20} for repo, path in GT
    ],
}


def _scorer_argv(script: Path, workdir: Path) -> list[str] | None:
    """The arguments ``script`` really hands the scorer, or None if it never runs it.

    Captured from the REAL post-shell-expansion argv via a PATH shim standing in for
    ``python3``, never parsed from the script text. That is what makes it robust to the
    spellings a text scan trips on — ``--keys=a,b``, a ``$KEYS`` variable, a
    line-continuation reformat — because the shim reads argv after the shell is done
    with it. (An earlier plan to regex the script text was rejected for exactly that
    fragility.)

    Robust to those spellings of a ``-m`` invocation, and no further: the shim matches the
    module as a standalone argument, so an import through ``python3 -c`` slips past it,
    and a name built at runtime (``-m eb_verify.scorers.$NAME``) never even clears the
    prefilter. Both would drop a real caller quietly. Neither is reachable today — every
    shipped caller execs ``-m`` with a literal name — and EnterpriseBench-51boy holds the
    evidence and a fix sketch for when that stops being true.

    Running it is also what separates a script that USES the scorer from one that
    merely names it; ``_discover_file_extraction_checks`` explains why that matters.
    """
    bindir = workdir / "shimbin"
    bindir.mkdir(exist_ok=True)
    dump = workdir / "argv.txt"
    # A bash shim (never `#!/usr/bin/env python3`, which would re-invoke itself and
    # recurse). It records argv ONLY for the scorer invocation and delegates every
    # other python3 call to the real interpreter, so a future adopter that runs python3
    # for setup before the scorer is not silently swallowed — the corpus auto-adopts
    # check scripts by content-glob, so this test must survive scripts it has not seen.
    shim = bindir / "python3"
    shim.write_text(
        "#!/usr/bin/env bash\n"
        'for a in "$@"; do\n'
        f'  if [ "$a" = {shlex.quote(SCORER_MODULE)} ]; then\n'
        f'    printf "%s\\n" "$@" > {shlex.quote(str(dump))}\n'
        "    exit 0\n"
        "  fi\n"
        "done\n"
        f'exec {shlex.quote(sys.executable)} "$@"\n'
    )
    shim.chmod(0o755)

    workspace, task_dir = _stage_workspace(workdir, PROBE_ANSWER)
    env = checkpoint_env(workspace, task_dir, "scorer-argv-probe")
    env["PATH"] = str(bindir) + os.pathsep + env["PATH"]

    # No check=True: the shim short-circuits the scorer (exit 0, no verdict printed), so
    # a script that post-processes the scorer's output can legitimately fail afterwards.
    # The dump's existence is the signal that the scorer was reached, not the exit status.
    subprocess.run(
        ["bash", str(script)],
        capture_output=True, text=True, cwd=str(workspace),
        env=env, timeout=30,  # a hung script must fail this gate, not stall CI forever
    )
    if not dump.exists():
        return None
    # The shim dumps only when the module token is in argv, so index() cannot raise.
    argv = dump.read_text().splitlines()
    return argv[argv.index(SCORER_MODULE) + 1:]


def _discover_file_extraction_checks(root: Path = REPO_ROOT) -> tuple[list[Path], list[str]]:
    """The check scripts under ``root`` that really exec the scorer, and the ones that
    could not be probed at all.

    Discovered by content, never by name. A task rename, or the 26 further check
    scripts bead rmz1x wants pointed at this scorer, are covered automatically; a
    hardcoded task list would leave every future adopter unguarded.

    Two stages, because naming the module and running it are different things. The
    substring is a PREFILTER only — a necessary condition, cheap enough to read across
    all 478 check scripts, where executing all of them would not be. Execution is the
    confirmation, and it is the ground truth: calibration-001 names the module in a prose
    comment and scores via ``eb_verify.plugins.path_match`` instead, so a substring test
    adopted it and then failed it for "passing no --keys to the scorer" — a check that
    was never its to pass.

    A script neither stage can get an answer out of — unreadable, not UTF-8, hangs, will
    not start — is REPORTED, never counted as "not a caller". That quiet reading would
    drop a real caller the moment its script broke, shrinking this gate while it stayed
    green. Nor may the error escape: BOTH stages run at import, to feed ``parametrize``,
    and an escaping error there aborts collection for the whole SESSION — every test in
    tests/integrity/, not just this file's, behind one message. Reporting keeps the blame
    on the one script at fault. Both stages funnel into the same list for that reason;
    the prefilter earns it too, since a file it cannot read may well be a caller.

    ``root`` is a parameter so the reduction can be tested against a synthetic tree; the
    corpus itself always takes the default.
    """
    unprobeable: list[str] = []
    candidates: list[Path] = []
    for path in sorted(root.glob("benchmarks/*/*/checks/*.sh")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            unprobeable.append(f"{path.relative_to(root)}: {exc!r}")
            continue
        if SCORER_MODULE in text:
            candidates.append(path)

    confirmed: list[Path] = []
    for script in candidates:
        with tempfile.TemporaryDirectory() as probe_dir:
            try:
                argv = _scorer_argv(script, Path(probe_dir))
            except (subprocess.TimeoutExpired, OSError) as exc:
                unprobeable.append(f"{script.relative_to(root)}: {exc!r}")
                continue
        if argv is not None:
            confirmed.append(script)
    return confirmed, unprobeable


FILE_EXTRACTION_CHECKS, UNPROBEABLE_CHECKS = _discover_file_extraction_checks()


def test_a_script_the_prefilter_cannot_even_read_is_reported_not_skipped(tmp_path):
    """The prefilter has to fail the same way the probe does.

    It reads before it filters, so a stray non-UTF-8 byte raises where no ``--keys`` ever
    would — and ``UnicodeDecodeError`` is not an ``OSError``, so the probe's own guard
    would not have caught it. Unread is not the same as uninteresting: the file might have
    named the scorer. Skipping it would shrink the gate in silence; letting it escape
    would abort collection for every test in tests/integrity/ at once.
    """
    checks = tmp_path / "benchmarks" / "suite" / "task" / "checks"
    checks.mkdir(parents=True)
    (checks / "check.sh").write_bytes(b"#!/usr/bin/env bash\n# \xff\xfe not utf-8\n")

    confirmed, unprobeable = _discover_file_extraction_checks(tmp_path)

    assert confirmed == []
    assert len(unprobeable) == 1
    assert "check.sh" in unprobeable[0]


def test_every_candidate_script_could_actually_be_probed():
    """Second non-vacuity guard, for the scripts discovery could not run.

    The corpus shrinking is the failure this file exists to catch, so a candidate that
    hangs or will not start has to say so out loud, naming itself, instead of leaving
    through the same door as a script that simply scores by other means.
    """
    assert not UNPROBEABLE_CHECKS, (
        "candidate check scripts could not be probed, so discovery may have dropped a "
        f"real scorer caller instead of confirming it: {UNPROBEABLE_CHECKS}"
    )


def test_the_corpus_actually_found_the_scorers_call_sites():
    """Non-vacuity guard. Without it a rename empties the glob, every vector below
    passes by iterating nothing, and the gate goes green guarding nothing."""
    assert len(FILE_EXTRACTION_CHECKS) >= 2, (
        "no shipped check script execs eb_verify.scorers.file_extraction, so the "
        "vectors below would all pass vacuously"
    )


def test_naming_the_scorer_in_a_comment_is_not_using_it(tmp_path):
    """A script that only mentions the module scores by other means and is not ours.

    The half of the predicate that keeps calibration-001 — which names the module in a
    comment and scores via ``path_match`` — out of a corpus whose every vector assumes
    the scorer runs.
    """
    script = tmp_path / "comment_only.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        f"# scores via path_match, which reuses the canonical {SCORER_MODULE} matcher\n"
        'echo \'{"score": 1.0, "passed": true, "detail": "scored elsewhere"}\'\n'
    )
    assert _scorer_argv(script, tmp_path) is None


def test_an_exec_of_the_scorer_is_discovered_with_its_real_argv(tmp_path):
    """The other half: a predicate that discovered NOTHING would also turn this gate
    green, so pair every exclusion above with a positive case."""
    script = tmp_path / "real_call.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        f"exec python3 -m {SCORER_MODULE} \\\n"
        "    --keys source_files,files\n"
    )
    assert _scorer_argv(script, tmp_path) == ["--keys", "source_files,files"]


def test_a_script_that_guards_its_inputs_before_scoring_is_still_discovered(tmp_path):
    """The probe must stage what a check script's opening guards demand.

    Pins ``_stage_workspace``: probed in a bare workspace, a hardened script exits at
    its guard and looks exactly like one that does not use the scorer, so a real caller
    would drop out of the corpus silently and this gate would shrink while staying green.
    """
    script = tmp_path / "hardened.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'if [[ ! -f "${TASK_DIR:-}/ground_truth.json" ]]; then\n'
        '  echo \'{"score": 0.0, "passed": false, "detail": "VERIFIER_INFRA_ERROR"}\'; exit 0\n'
        "fi\n"
        'if [[ ! -f "$WORKSPACE/agent_output/answer.json" ]]; then\n'
        '  echo \'{"score": 0.0, "passed": false, "detail": "No answer.json found"}\'; exit 0\n'
        "fi\n"
        f"exec python3 -m {SCORER_MODULE} --keys citations\n"
    )
    assert _scorer_argv(script, tmp_path) == ["--keys", "citations"]


def test_discovery_keeps_the_real_caller_and_drops_the_comment_only_one(tmp_path):
    """The two-stage reduction end to end, on a synthetic tree.

    The predicate tests above pin ``_scorer_argv``; this pins the wiring that consumes
    it. Reverting discovery to the bare substring test keeps every test above green —
    only this one goes red — so the fix stays nailed down at the level it was made.
    """
    checks = tmp_path / "benchmarks" / "suite"
    real = checks / "real-task" / "checks"
    comment_only = checks / "prose-task" / "checks"
    real.mkdir(parents=True)
    comment_only.mkdir(parents=True)
    (real / "check.sh").write_text(
        f"#!/usr/bin/env bash\nexec python3 -m {SCORER_MODULE} --keys files\n"
    )
    (comment_only / "check.sh").write_text(
        "#!/usr/bin/env bash\n"
        f"# scores via path_match, which reuses the canonical {SCORER_MODULE} matcher\n"
        'echo \'{"score": 1.0, "passed": true, "detail": "scored elsewhere"}\'\n'
    )
    assert _discover_file_extraction_checks(tmp_path) == ([real / "check.sh"], [])


def run_shipped_check(script: Path, answer, tmp_path) -> dict:
    """Score ``answer`` by running the real check script, exactly as the runner does.

    ``bash <script>`` with ``cwd=workspace`` and ``checkpoint_env`` mirrors
    ``CheckpointRunner.run_checkpoint``, so the script's own ``--keys`` reaches the
    scorer untouched — a key dropped from the shipped artifact surfaces here as the
    false zero it would be in a real run.
    """
    workspace, task_dir = _stage_workspace(tmp_path, answer)

    proc = subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        cwd=str(workspace),
        env=checkpoint_env(workspace, task_dir, "integrity-vector"),
        timeout=30,  # as every other check-script runner in tests/ does: a hung
                     # script must fail this gate, not stall CI on it forever
    )
    assert proc.stdout, f"{script.name} printed no verdict at all (stderr: {proc.stderr})"
    return json.loads(proc.stdout)


def shipped_keys(script: Path, tmp_path) -> set[str]:
    """The ``--keys`` a shipped check script actually passes to the scorer.

    Reads the real argv through the same probe that discovered ``script`` in the first
    place, so key-capture and discovery cannot disagree about whether the scorer ran —
    their disagreement was the defect this shared helper closes.

    The argv goes to the scorer's own parser, so ``--keys a,b`` and ``--keys=a,b`` both
    normalize the one way the scorer itself normalizes them.
    """
    scorer_argv = _scorer_argv(script, tmp_path)
    if scorer_argv is None:
        return set()  # the script never invoked the scorer; the caller asserts non-vacuity
    try:
        raw = build_parser().parse_known_args(scorer_argv)[0].keys or ""
    except HarnessError:
        return set()  # no --keys at all; non-vacuity assertion in the test reports it
    return {k.strip() for k in raw.split(",") if k.strip()}


# One answer shape per key the shipped --keys must carry, so that dropping ANY key
# from a check script turns this gate red. Derived by mutation, not by reading the
# scripts: with a vector per key, `sed -i 's/,<key>//'` on a shipped script fails
# exactly the case that names it.
#
# Coverage is the point, not variety. Scorer-internal behaviour (the full citation
# dialect matrix, the ambiguity rule, the nested-ground-truth case) is exercised at
# the unit layer in tests/test_file_extraction.py, where it does not cost a
# merge-blocking gate a subprocess per case and cannot drift from a second copy of
# the same table. What lives here is only what depends on the shipped artifact.
#
# `source_files` carries a citation suffix so that one end-to-end dialect case does
# cross the real script — the suffix strip and the key list are the two halves of the
# same false zero.
ANSWER_SHAPES = {
    "source_files": {"source_files": [f"{path}:120-140" for path in ABSOLUTE]},
    "files": {"source_files": ["totally/unrelated.py"], "files": ABSOLUTE},
    "error_source.files": {"error_source": {"files": ABSOLUTE}},
    "code_paths": {"code_paths": [{"path": path} for path in ABSOLUTE]},
    "citations": {"citations": [
        {"repo": repo, "file": path, "evidence_span": "x" * 20} for repo, path in GT
    ]},
}


@pytest.mark.parametrize(
    "script",
    FILE_EXTRACTION_CHECKS,
    ids=[path.parent.parent.name for path in FILE_EXTRACTION_CHECKS],
)
@pytest.mark.parametrize("key", list(ANSWER_SHAPES), ids=list(ANSWER_SHAPES))
def test_omitted_mandated_keys_zero_a_spec_compliant_answer(script, key, tmp_path):
    """Every key the shipped --keys advertises must actually score.

    run_task.py's appendix mandates `code_paths` in every task's instructions, and
    require_grounded_citations adds a mandatory `citations` list, so an agent that
    followed its instructions to the letter must not be scored 0.0 on a 0.40-weight
    checkpoint because the check script omitted the key it was told to use. The other
    three keys are the shapes the scorer promises to accept; a key silently dropped
    from a script is a false zero for every agent that used it.

    The `files` case doubles as the first-key-wins guard: the answer is wrong under
    the earlier `source_files` and right under the later `files`, so it only scores
    if the keys are unioned rather than stopping at the first populated one.
    """
    payload = run_shipped_check(script, ANSWER_SHAPES[key], tmp_path)
    assert payload["score"] == 1.0, f"--keys is missing {key!r}: {payload['detail']}"
    assert payload["passed"] is True


@pytest.mark.parametrize(
    "script",
    FILE_EXTRACTION_CHECKS,
    ids=[path.parent.parent.name for path in FILE_EXTRACTION_CHECKS],
)
def test_every_shipped_key_has_a_covering_vector(script, tmp_path):
    """A key ADDED to a shipped ``--keys`` must not go uncovered.

    The parametrized test above catches a key REMOVED — its answer shape drops to 0.0.
    This catches the other direction: a new key with no vector in ``ANSWER_SHAPES``
    would be a silent false zero for every agent that answered under it, and nothing
    would notice (adding ``,evidence_files`` to a shipped script left the gate green).
    Together the two force ``ANSWER_SHAPES`` to equal the shipped key set — one
    advertised case per shipped entry, no more and no fewer.

    The shipped keys are DISCOVERED BY EXECUTION (``shipped_keys`` captures the real
    argv), never restated here, so this cannot drift from the artifact the way a copied
    key list would.
    """
    keys = shipped_keys(script, tmp_path)
    assert keys, f"{script} passed no --keys to the scorer"  # non-vacuity
    uncovered = keys - set(ANSWER_SHAPES)
    assert not uncovered, (
        f"{script.parent.parent.name} ships --keys {sorted(keys)} but ANSWER_SHAPES "
        f"exercises no answer shape for {sorted(uncovered)}; a dropped or added key "
        f"would false-zero a spec-compliant answer with no gate catching it"
    )


def test_checkpoint_env_prepends_the_lib_dir_to_pythonpath(tmp_path):
    """A DIRECT guard on the PYTHONPATH export, not one riding on an import succeeding.

    Every execution-based vector above imports eb_verify via `python -m`, and CI
    pip-installs lib/, so that import resolves with OR without PYTHONPATH — a change
    that silently dropped the export from checkpoint_env would ship green through all of
    them. This asserts the built env dict itself against the runner's own _LIB_DIR, so
    the export is guarded regardless of how eb_verify happens to be installed. Pure unit
    check: it never runs on the shipped scorer import path, so it cannot itself become a
    false-zero source in the sandbox.
    """
    env = checkpoint_env(tmp_path / "ws", tmp_path / "task", "probe")
    first = env["PYTHONPATH"].split(os.pathsep)[0]
    assert first == str(_LIB_DIR), (
        f"checkpoint_env must prepend the lib dir to PYTHONPATH; got {env['PYTHONPATH']!r}"
    )
