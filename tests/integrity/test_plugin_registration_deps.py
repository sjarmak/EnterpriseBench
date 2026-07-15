"""fact_triples must be registered only when its heavy deps are actually usable.

The scoring stack (numpy/scikit-learn) is imported lazily so that importers which
never score facts do not pay ~0.8s and ~100MB of TF-IDF machinery at startup.

That deferral silently defeated the old capability probe. The probe registered
FactTriplesValidator unless ``import fact_triples`` raised ImportError; once the
numpy import moved inside the functions that use it, the module imported cleanly
on a numpy-less sandbox, the validator registered, and the deferred ``import
numpy`` blew up later -- inside ``validate()``, at scoring time, where
``runner.py`` calls it with no try/except. Harness breakage destroyed the run
instead of yielding a clean, scoreable record.

These tests pin both halves of the invariant, which pull in opposite directions:
registration must consult the deps explicitly (not as an import side effect), and
the probe itself must not import them. Each runs in a fresh interpreter, because
import state is process-global and numpy is long since imported by the time the
suite reaches this module.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from eb_verify.scorer_guard import _detail_infra_signature
from tests.integrity._probe import (
    HEAVY_ROOTS,
    LIB,
    modules_pulled_by,
    nonstdlib_modules,
    run_in_fresh_interpreter,
)

SCORER_MODULE = "eb_verify.scorers.file_extraction"


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


def _fact_triples_workspace(tmp_path: Path) -> Path:
    """A schema-valid, groundedness-passing workspace that reaches the embedder.

    The candidate statement deliberately does not exact-match the ground truth, so
    scoring must fall through to TF-IDF similarity — the lazy-import site. A workspace
    that short-circuits earlier (no facts.json, bad schema) would never touch numpy and
    would make these tests pass for the wrong reason.
    """
    workspace = tmp_path / "ws"
    (workspace / "repo").mkdir(parents=True)
    (workspace / "ground_truth").mkdir()

    span = "score = 1.0 if passed else 0.0"
    (workspace / "repo" / "milestone.py").write_text(f"def run():\n    {span}\n")
    (workspace / "facts.json").write_text(
        json.dumps(
            {
                "facts": [
                    {
                        "subject": "milestone.py",
                        "predicate": "fabricates",
                        "object": "scores",
                        "statement": (
                            "milestone.py fabricates a score from the process exit code"
                        ),
                        "evidence": {
                            "repo": "repo",
                            "file": "milestone.py",
                            "span": span,
                        },
                        "confidence": 90,
                    }
                ]
            }
        )
    )
    (workspace / "ground_truth" / "expected_facts.json").write_text(
        json.dumps(
            {
                "facts": [
                    {
                        "subject": "milestone.py",
                        "predicate": "invents",
                        "object": "scores",
                        "statement": (
                            "The third runner invents a score from the process exit status"
                        ),
                    }
                ]
            }
        )
    )
    return workspace


class TestRegistrationRequiresUsableDeps:
    """Without numpy, the validator must not register -- and must say so."""

    def test_validator_not_registered_when_numpy_absent(self) -> None:
        out = run_in_fresh_interpreter(
            """
            from eb_verify.plugins import get_validator
            print("REGISTERED" if get_validator("fact_triples") else "ABSENT")
            """,
            block_deps=True,
        )
        assert "ABSENT" in out, (
            "fact_triples registered on a numpy-less sandbox. The lazy import means "
            "a clean `import fact_triples` no longer proves numpy is usable; "
            "registration must probe the deps explicitly."
        )

    def test_absent_validator_is_announced_not_silent(self) -> None:
        out = run_in_fresh_interpreter(
            """
            import warnings
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                import eb_verify.plugins  # noqa: F401
            print("WARNED" if any(
                issubclass(w.category, RuntimeWarning) for w in caught
            ) else "SILENT")
            """,
            block_deps=True,
        )
        assert "WARNED" in out, "dropping a validator must not be silent"

    def test_validator_registered_when_deps_present(self) -> None:
        """The guard must not over-fire: a normal install still scores facts."""
        pytest.importorskip("numpy")
        pytest.importorskip("sklearn")
        out = run_in_fresh_interpreter(
            """
            from eb_verify.plugins import get_validator
            print("REGISTERED" if get_validator("fact_triples") else "ABSENT")
            """,
        )
        assert "REGISTERED" in out, "deps are installed; the validator must register"


class TestNoImportErrorReachesScoring:
    """The failure this bead exists to eliminate: harness breakage killing a run."""

    def test_missing_numpy_never_escapes_as_importerror_at_scoring(
        self, tmp_path: Path
    ) -> None:
        """A numpy-less sandbox must yield a clean record, not a dead process.

        ``runner.py`` calls ``validator.validate(workspace)`` unguarded, so an
        ImportError escaping ``validate()`` takes down the whole verification run.
        Score the artifact through whatever the registry hands back: either the
        validator is absent (the runner reports the unknown type and scores on),
        or it is present and must not raise ImportError.
        """
        workspace = _fact_triples_workspace(tmp_path)
        out = run_in_fresh_interpreter(
            f"""
            import pathlib
            from eb_verify.plugins import get_validator

            validator = get_validator("fact_triples")
            if validator is None:
                print("NO_VALIDATOR")  # runner reports the unknown type; run survives
            else:
                try:
                    validator.validate(pathlib.Path({str(workspace)!r}))
                    print("SCORED")
                except ImportError as exc:
                    print(f"IMPORTERROR_ESCAPED {{exc}}")
            """,
            block_deps=True,
        )
        assert "IMPORTERROR_ESCAPED" not in out, (
            "a missing dependency escaped validate() as an ImportError; "
            "runner.py calls validate() unguarded, so this kills the entire run"
        )
        assert "NO_VALIDATOR" in out


class TestBrokenInstallCannotKillTheRun:
    """A dependency can be findable and still unusable, and the probe cannot tell.

    ``find_spec`` resolves a module without executing it — that is precisely why the
    probe is cheap enough to sit on the chain-runner import path. The cost is that a
    *present but broken* numpy (ABI mismatch, half-installed, corrupt .so) satisfies
    the probe and only fails when something finally imports it, inside validate().

    The old module-scope probe caught that case for free, because it really did run
    the import. So the probe alone is a narrower version of the same regression, and
    the runner must hold the line: a validator that raises ImportError yields a
    record, not a dead process.
    """

    def _shadow_broken_numpy(self, tmp_path: Path, exc: str = "ImportError") -> Path:
        """A numpy that find_spec resolves happily and that explodes on execution."""
        shadow = tmp_path / f"shadow_{exc}"
        shadow.mkdir()
        (shadow / "numpy.py").write_text(
            f'raise {exc}("numpy: libopenblas.so: cannot open shared object file '
            '(simulated corrupt install)")\n'
        )
        return shadow

    def test_broken_numpy_is_findable_but_unimportable(self, tmp_path: Path) -> None:
        """Guard the premise: a vacuous shadow would make the next test meaningless."""
        out = run_in_fresh_interpreter(
            """
            import importlib.util
            print("FOUND" if importlib.util.find_spec("numpy") else "NOTFOUND")
            try:
                import numpy  # noqa: F401
                print("IMPORTED")
            except ImportError:
                print("IMPORT_RAISES")
            """,
            extra_path=self._shadow_broken_numpy(tmp_path),
        )
        assert "FOUND" in out and "IMPORT_RAISES" in out, (
            f"the broken-numpy shadow does not exercise the gap it exists to test: {out}"
        )

    def test_broken_numpy_yields_a_record_not_a_dead_process(
        self, tmp_path: Path
    ) -> None:
        """validate() must absorb its own dependency fault, for every caller.

        runner.validate_artifacts() and cli both call validate() unguarded, so the
        guard belongs in the validator rather than at each call site.
        """
        workspace = _fact_triples_workspace(tmp_path)
        out = run_in_fresh_interpreter(
            f"""
            import pathlib
            from eb_verify.plugins import get_validator

            validator = get_validator("fact_triples")
            print(f"REGISTERED={{validator is not None}}")
            if validator is not None:
                try:
                    result = validator.validate(pathlib.Path({str(workspace)!r}))
                    print(f"RECORDED valid={{result.valid}} :: {{result.detail}}")
                except ImportError as exc:
                    print(f"IMPORTERROR_ESCAPED {{exc}}")
            """,
            extra_path=self._shadow_broken_numpy(tmp_path),
        )
        assert "IMPORTERROR_ESCAPED" not in out, (
            "a broken numpy escaped validate() as an ImportError. runner.py and cli.py "
            "call validate() unguarded, so this aborts the entire verification run over "
            f"a dependency fault that is not the agent's doing. Got: {out.strip()}"
        )
        assert "RECORDED" in out, out

    # A broken dependency is under no obligation to raise ImportError: an ABI mismatch
    # raises RuntimeError, a truncated .so raises OSError, a bad C extension raises
    # SystemError. Guarding only ImportError leaves the run just as dead.
    @pytest.mark.parametrize(
        "exc", ["ImportError", "OSError", "SystemError", "RuntimeError", "ValueError"]
    )
    def test_any_import_failure_yields_a_record_not_a_dead_process(
        self, tmp_path: Path, exc: str
    ) -> None:
        workspace = _fact_triples_workspace(tmp_path)
        out = run_in_fresh_interpreter(
            f"""
            import pathlib
            from eb_verify.plugins import get_validator

            validator = get_validator("fact_triples")
            if validator is None:
                print("NO_VALIDATOR")
            else:
                try:
                    result = validator.validate(pathlib.Path({str(workspace)!r}))
                    print(f"RECORDED valid={{result.valid}} :: {{result.detail}}")
                except BaseException as exc:  # noqa: BLE001 — anything escaping is the bug
                    print(f"ESCAPED {{type(exc).__name__}}: {{exc}}")
            """,
            extra_path=self._shadow_broken_numpy(tmp_path, exc),
        )
        assert "ESCAPED" not in out, (
            f"a numpy raising {exc} on import escaped validate() and killed the run. "
            "Only ImportError is guarded, but module-level code can raise anything; "
            f"the dependency load must be guarded on failure, not on type. Got: {out.strip()}"
        )
        assert "RECORDED" in out, out

    def test_process_control_still_propagates(self, tmp_path: Path) -> None:
        """The guard stops at Exception on purpose.

        A KeyboardInterrupt or SystemExit arriving mid-import is process control, not a
        broken dependency. Swallowing it into "dependency unavailable" would make the
        verifier unkillable and mask a deliberate exit, so it must keep propagating.
        """
        out = run_in_fresh_interpreter(
            f"""
            import pathlib
            from eb_verify.plugins import get_validator

            validator = get_validator("fact_triples")
            try:
                validator.validate(pathlib.Path({str(_fact_triples_workspace(tmp_path))!r}))
                print("SWALLOWED")
            except SystemExit:
                print("PROPAGATED")
            """,
            extra_path=self._shadow_broken_numpy(tmp_path, "SystemExit"),
        )
        assert "PROPAGATED" in out, (
            f"SystemExit was swallowed by the dependency guard: {out.strip()}"
        )


class TestProbeStaysCheap:
    """The probe must not undo the deferral it exists to protect."""

    def test_registry_import_does_not_pull_numpy(self) -> None:
        """Importing the plugin registry must not drag in the TF-IDF stack.

        ``plugins/__init__`` imports every validator eagerly, so a probe that really
        imports numpy re-imposes the ~0.8s/~100MB cost on every consumer of the
        registry. This equally forbids "fixing" the registration bug by reverting
        the lazy import.

        It probes ``eb_verify.plugins`` directly rather than through ``scorer_guard``:
        the guard no longer reaches the registry (see ``TestScorerGuardStaysIsolated``),
        so probing via the guard would pass vacuously.
        """
        heavy = sorted(
            {m.split(".")[0] for m in modules_pulled_by("eb_verify.plugins")}
            & set(HEAVY_ROOTS)
        )
        assert not heavy, (
            f"the registry import pulled the heavy scoring stack ({heavy}); "
            "the numpy/sklearn imports must stay deferred and the probe must not execute them"
        )


class TestScorerGuardStaysIsolated:
    """The harness-failure guard must not depend on the stack it reports on."""

    # The guard needs ``redact`` to bound the detail strings it reports; a stdlib-only
    # sibling cannot break in a way the guard exists to survive. Anything else -- the
    # registry, the 9 validators, ``runner``, a third-party dep -- is a module that can
    # blind the very thing that reports it being broken.
    GUARD_MAY_REACH = {"eb_verify", "eb_verify.scorer_guard", "eb_verify.redact"}

    def test_importing_scorer_guard_reaches_nothing_that_can_blind_it(self) -> None:
        """``scorer_guard`` imports stdlib and ``redact`` -- its import must stay that cheap.

        It exists to report harness failures, so it must not be importable-only-if the
        harness is healthy: a broken import in any one of the 9 unguarded validators
        would otherwise take down the very module that reports that class of failure.

        One allowlist rather than a stdlib check plus a sibling check: "reaches nothing
        outside this set" already fails on numpy AND on eb_verify.plugins, and unlike a
        denylist it also fails on whatever the guard acquires next -- which is the
        regression worth catching. A new entry here is only acceptable if it is
        stdlib-only and the guard genuinely needs it.
        """
        reached = nonstdlib_modules(modules_pulled_by("eb_verify.scorer_guard"))
        assert reached <= self.GUARD_MAY_REACH, (
            f"importing eb_verify.scorer_guard dragged in unvetted modules "
            f"({sorted(reached - self.GUARD_MAY_REACH)}); the guard must stay importable "
            "when a validator is broken or a dependency is missing, so nothing may "
            "re-couple it to the plugin stack"
        )

    def test_the_broken_validator_shadow_actually_breaks_the_registry(
        self, broken_validator_tree: Path
    ) -> None:
        """Guard the premise: a vacuous shadow would make the next test meaningless."""
        out = run_in_fresh_interpreter(
            """
            try:
                import eb_verify.plugins  # noqa: F401
                print("REGISTRY_IMPORTED")
            except ImportError as exc:
                print("REGISTRY_RAISES:" + str(exc))
            """,
            extra_path=broken_validator_tree,
        )
        assert "REGISTRY_RAISES" in out, (
            "the broken-validator shadow does not break the plugin stack, so the "
            f"isolation test below would pass vacuously: {out.strip()}"
        )

    def test_scorer_guard_imports_while_the_plugin_stack_is_broken(
        self, broken_validator_tree: Path
    ) -> None:
        """The end the isolation exists for: a broken stack must not blind the guard."""
        out = run_in_fresh_interpreter(
            """
            import eb_verify.scorer_guard as guard
            print("GUARD_OK:" + guard.__file__)
            """,
            extra_path=broken_validator_tree,
        )
        assert "GUARD_OK:" in out, (
            f"the scorer guard could not be imported while the plugin stack was broken "
            f"({out.strip()}); the module that reports harness failure must not require "
            "a healthy harness"
        )
        # Assert the BROKEN tree is the one that answered, not the real lib/ still on
        # sys.path behind it -- otherwise this passes without ever exercising the break.
        assert str(broken_validator_tree) in out, (
            f"the guard resolved to a tree outside the broken shadow ({out.strip()}); "
            "the shadow is not on sys.path first, so this test proves nothing"
        )


class TestScorersPackageStaysImportLight:
    """What the scorer's location has to keep buying, stated as a test.

    ``python -m`` executes every parent ``__init__`` before ``main()``, so the import
    cost and the import risk of the scorer's package are paid on every checkpoint of
    every task attempt, before any code can report a failure. Nothing may quietly
    reintroduce an edge to the plugin registry or the scoring stack.
    """

    # What the scorer legitimately needs to print a guarded verdict, and nothing more.
    # The registry (a broken validator would empty its stdout, and the runner would book
    # the harness failure as an agent zero) and the scoring stack (it does not score
    # facts, and task sandboxes do not ship numpy) are both excluded by not appearing.
    SCORER_MAY_REACH = {
        "eb_verify",
        "eb_verify.scorers",
        "eb_verify.scorers.file_extraction",
        "eb_verify.scorer_guard",
        "eb_verify.redact",
    }

    def test_importing_the_scorer_reaches_nothing_it_does_not_need(self) -> None:
        """Stated as an allowlist, for the same reason the guard's isolation is.

        The tempting form is a denylist of the registry plus the heavy roots, but that
        only ever catches the two edges someone already thought of: a scorer that
        acquired ``jsonschema``, ``yaml``, or ``eb_verify.fact_coverage`` would read as
        clean -- and ``fact_coverage`` is exactly the module that would drag numpy back
        in transitively while a root-name check reported nothing heavy.
        """
        reached = nonstdlib_modules(modules_pulled_by(SCORER_MODULE))
        assert reached <= self.SCORER_MAY_REACH, (
            f"the shipped scorer reached modules it does not need "
            f"({sorted(reached - self.SCORER_MAY_REACH)}); every one of them is a module "
            "that can fail to import on a task sandbox and empty the scorer's stdout, "
            "which the runner books as a real agent zero"
        )

    def test_the_scorers_package_itself_has_no_import_side_effects(self) -> None:
        """The package is the contract: it must add nothing to what its modules cost."""
        pulled = modules_pulled_by("eb_verify.scorers") - {"eb_verify", "eb_verify.scorers"}
        assert not pulled, (
            f"eb_verify.scorers imports modules at package import ({sorted(pulled)}); it "
            "exists to be the location that does not, so its submodules pay only for "
            "what they use"
        )


class TestShippedScorerSurvivesABrokenValidator:
    """A broken validator must not silence the scorer that checkpoints exec.

    The guard being importable (above) is necessary but not sufficient: what the
    benchmark actually runs is ``python -m`` on the scorer, and runpy executes every
    parent package ``__init__`` before ``main()``'s try/except gets to report anything.
    While the scorer lived in ``eb_verify.plugins``, that meant one broken sibling
    validator emptied stdout and the runner fell back to exit-code scoring -- booking
    a harness failure as a real agent zero, which is the whole reason this module has
    a guard at all.
    """

    def _run_scorer(self, tree: Path, workspace: Path) -> subprocess.CompletedProcess:
        """Exec the scorer with ``tree`` as the ONLY source of ``eb_verify``.

        Deliberately not ``tree:LIB``: with the real lib behind it on the path, a
        scorer that failed to resolve out of the broken tree would quietly answer
        from the healthy one and the vectors below would pass without ever meeting
        the break. The tree is a whole copy of the package, so it needs no fallback.
        """
        env = {
            **os.environ,
            "PYTHONPATH": str(tree),
            "ANSWER_FILE": str(workspace / "answer.json"),
            "GT_FILE": str(workspace / "ground_truth.json"),
        }
        return subprocess.run(
            [sys.executable, "-m", SCORER_MODULE, "--keys", "source_files"],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )

    def _workspace(self, tmp_path: Path) -> Path:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        (workspace / "answer.json").write_text(
            json.dumps({"source_files": ["src/a.py"]}), encoding="utf-8"
        )
        (workspace / "ground_truth.json").write_text(
            json.dumps({"required_files": [{"path": "src/a.py", "repo": "r"}]}),
            encoding="utf-8",
        )
        return workspace

    def test_scorer_scores_a_matching_answer_on_a_healthy_tree(
        self, tmp_path: Path
    ) -> None:
        """Guard the premise: pins what the broken-tree run below must reproduce."""
        proc = self._run_scorer(LIB, self._workspace(tmp_path))
        verdict = json.loads(proc.stdout)
        assert (verdict["score"], verdict["passed"], proc.returncode) == (1.0, True, 0), (
            f"the scorer does not score a matching answer on a healthy tree "
            f"({proc.stdout!r}, rc={proc.returncode}); the vector below compares against "
            "this result, so it would prove nothing"
        )

    def test_a_broken_validator_is_invisible_to_the_scorer(
        self, broken_validator_tree: Path, tmp_path: Path
    ) -> None:
        """The headline invariant, and the shape of the bug if it regresses.

        Asserted as "identical to the healthy verdict" rather than "prints some JSON":
        the scorer does not import the registry, so a broken validator is not something
        it survives -- it is something it never meets. Anything re-coupling the two
        shows up here first as an empty stdout (runner.py then fabricates a score from
        the exit code and books the harness failure as a real agent zero), and a
        weaker assertion would let a degraded-but-parseable verdict through.
        """
        proc = self._run_scorer(broken_validator_tree, self._workspace(tmp_path))

        assert proc.stdout.strip(), (
            "the scorer printed NOTHING to stdout with a sibling validator broken "
            f"(rc={proc.returncode}, stderr={proc.stderr[-400:]!r}); runner.py then "
            "fabricates a score from the exit code, and scorer_guard cannot tell that "
            "0.0 from a real agent zero -- a harness failure booked as agent performance"
        )
        verdict = json.loads(proc.stdout)
        assert (verdict["score"], verdict["passed"], proc.returncode) == (1.0, True, 0), (
            f"a broken validator changed the scorer's verdict ({verdict}, rc={proc.returncode}); "
            "it must score exactly as it does on a healthy tree"
        )
        assert not _detail_infra_signature(verdict["detail"]), (
            f"the scorer reported a harness failure ({verdict['detail']!r}) over a broken "
            "validator it never uses; the checkpoint would be re-run rather than scored"
        )
