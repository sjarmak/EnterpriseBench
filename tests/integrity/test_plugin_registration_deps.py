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
import shutil
from pathlib import Path

import pytest

from tests.integrity.conftest import LIB, run_in_fresh_interpreter


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
            block_deps=False,
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
            block_deps=False,
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
            block_deps=False,
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
            block_deps=False,
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
            block_deps=False,
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
        out = run_in_fresh_interpreter(
            """
            import sys
            import eb_verify.plugins  # noqa: F401
            heavy = sorted({
                m.split(".")[0] for m in sys.modules
                if m.split(".")[0] in ("numpy", "sklearn", "scipy")
            })
            print("HEAVY:" + (",".join(heavy) if heavy else "none"))
            """,
            block_deps=False,
        )
        assert "HEAVY:none" in out, (
            f"the registry import pulled the heavy scoring stack ({out.strip()}); "
            "the numpy/sklearn imports must stay deferred and the probe must not execute them"
        )


class TestScorerGuardStaysIsolated:
    """The harness-failure guard must not depend on the stack it reports on."""

    def test_importing_scorer_guard_pulls_nothing_but_stdlib(self) -> None:
        """``scorer_guard`` imports stdlib only -- its import must stay that cheap.

        It exists to report harness failures, so it must not be importable-only-if
        the harness is healthy: a broken import in any one of the 9 unguarded
        validators would otherwise take down the very module that reports that
        class of failure.

        Asserted as "nothing outside the stdlib" rather than as a denylist of the
        modules it must not reach: a denylist is blind to whatever the guard acquires
        next, which is the regression worth catching.
        """
        out = run_in_fresh_interpreter(
            """
            import sys
            before = set(sys.modules)
            import eb_verify.scorer_guard  # noqa: F401
            roots = {m.split(".")[0] for m in set(sys.modules) - before}
            third_party = sorted(
                r for r in roots
                if r not in sys.stdlib_module_names and not r.startswith("_")
            )
            print("NONSTDLIB:" + (",".join(third_party) if third_party else "none"))
            """,
            block_deps=False,
        )
        assert "NONSTDLIB:eb_verify" in out and "," not in out.split("NONSTDLIB:")[1], (
            f"importing eb_verify.scorer_guard reached beyond the stdlib ({out.strip()}); "
            "the guard must stay importable when a validator is broken or a dependency "
            "is missing, so nothing may re-couple it to the plugin stack"
        )

    def test_importing_scorer_guard_pulls_no_sibling_eb_verify_module(self) -> None:
        """The guard's own package is the one non-stdlib root it may touch -- alone.

        ``eb_verify`` passes the stdlib check above by construction, so pin separately
        that it brings no siblings with it: ``runner``, the registry and the 9
        validators are exactly what must not ride along.
        """
        out = run_in_fresh_interpreter(
            """
            import sys
            import eb_verify.scorer_guard  # noqa: F401
            siblings = sorted(
                m for m in sys.modules
                if m.split(".")[0] == "eb_verify"
                and m not in ("eb_verify", "eb_verify.scorer_guard")
            )
            print("SIBLINGS:" + (",".join(siblings) if siblings else "none"))
            """,
            block_deps=False,
        )
        assert "SIBLINGS:none" in out, (
            f"importing eb_verify.scorer_guard dragged in sibling modules ({out.strip()}); "
            "the guard must stay importable when any of them is broken"
        )

    def _tree_with_a_broken_validator(self, tmp_path: Path) -> Path:
        """A copy of the real lib tree with one validator broken at import time.

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
        with (shadow / "eb_verify" / "plugins" / "call_graph.py").open("a") as fh:
            fh.write("\nimport eb_verify_simulated_broken_dep  # noqa: F401\n")
        return shadow

    def test_the_broken_validator_shadow_actually_breaks_the_registry(
        self, tmp_path: Path
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
            block_deps=False,
            extra_path=self._tree_with_a_broken_validator(tmp_path),
        )
        assert "REGISTRY_RAISES" in out, (
            "the broken-validator shadow does not break the plugin stack, so the "
            f"isolation test below would pass vacuously: {out.strip()}"
        )

    def test_scorer_guard_imports_while_the_plugin_stack_is_broken(
        self, tmp_path: Path
    ) -> None:
        """The end the isolation exists for: a broken stack must not blind the guard."""
        out = run_in_fresh_interpreter(
            """
            import eb_verify.scorer_guard as guard
            print("GUARD_OK:" + guard.__file__)
            """,
            block_deps=False,
            extra_path=self._tree_with_a_broken_validator(tmp_path),
        )
        assert "GUARD_OK:" in out, (
            f"the scorer guard could not be imported while the plugin stack was broken "
            f"({out.strip()}); the module that reports harness failure must not require "
            "a healthy harness"
        )
        # Assert the BROKEN tree is the one that answered, not the real lib/ still on
        # sys.path behind it -- otherwise this passes without ever exercising the break.
        assert str(tmp_path) in out, (
            f"the guard resolved to a tree outside the broken shadow ({out.strip()}); "
            "the shadow is not on sys.path first, so this test proves nothing"
        )
