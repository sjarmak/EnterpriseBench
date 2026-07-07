---
name: eb-build-and-test
description: >
  Set up the EnterpriseBench Python environment and run its test suite the way
  CI does. Load this skill when: `import eb_verify` fails with
  ModuleNotFoundError; you need to run pytest locally and match CI; `make test`
  reports "no tests collected"; pytest collection errors mention numpy,
  matplotlib, seaborn, codeprobe, or verifier_mutation_test; you are deciding
  which pytest markers to exclude; the fact_triples validator is missing from
  the plugin registry; scripts/audit_consistency.py crashes with
  FileNotFoundError; or you need to know why CI on main is red and what a
  green local baseline actually looks like. NOT for authoring or validating
  tasks (eb-task-authoring), running benchmark tasks in Docker
  (eb-sandbox-execution, eb-run-and-analyze), or scoring semantics
  (eb-checkpoint-scoring, eb-verification-library).
---

# EnterpriseBench: build and test

How to recreate the development environment from scratch and get test results
you can trust. All commands verified against the repo on 2026-07-07. Run
everything from the repo root.

## When NOT to use this skill

| You want to...                                      | Use instead                                                 |
| --------------------------------------------------- | ----------------------------------------------------------- |
| Understand what EnterpriseBench is, repo layout     | eb-orientation                                              |
| Add or fix a task, run `make verify` gates          | eb-task-authoring, eb-crnt-and-task-mix                     |
| Run a benchmark task in its Docker sandbox          | eb-sandbox-execution                                        |
| Run a campaign, analyze results, regenerate figures | eb-run-and-analyze                                          |
| Understand how scores are computed                  | eb-checkpoint-scoring                                       |
| Work on `lib/eb_verify/` validators                 | eb-verification-library                                     |
| Know how changes are gated and dispatched           | eb-scoring-integrity-doctrine, eb-git-and-dispatch-workflow |

## 1. Environment from scratch

The verification library lives at `lib/` as an installable package named
`eb-verify`. It is NOT on the default Python path: a bare
`python3 -c "import eb_verify"` fails with `ModuleNotFoundError` until you
install it.

CI (`.github/workflows/ci.yml`) uses Python 3.12; `lib/pyproject.toml`
declares `requires-python = ">=3.10"`. The repo has a local `venv/`
(git-ignored, lines 8-9 of `.gitignore`; it is a developer convenience, not a
checked-in artifact).

Minimal environment, exactly what CI installs:

```bash
python3 -m venv venv
venv/bin/pip install pytest jsonschema tomli
venv/bin/pip install -e lib/
```

That gets you `eb_verify` (and, if the untracked `lib/eb_metrics/` directory
is present in your checkout, `eb_metrics` too; both are mapped by the same
editable install). `tomli` is only required on Python < 3.11 but CI installs
it unconditionally.

**The minimal set is NOT enough to collect the full test suite.** Four
tracked test modules import heavy libraries at module top with no
`importorskip` guard. For a suite that collects cleanly, also install:

```bash
venv/bin/pip install numpy scikit-learn matplotlib seaborn
```

Why each is needed (verified by reading the import chains):

| Missing package | Breaks collection of                                                 | Import chain                                                                                  |
| --------------- | -------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| numpy           | `tests/test_fact_coverage.py`, `tests/test_fact_triples_verifier.py` | direct `import numpy`                                                                         |
| scikit-learn    | same two modules                                                     | `eb_verify/fact_coverage.py:71` imports `sklearn.feature_extraction.text.TfidfVectorizer`     |
| matplotlib      | `tests/test_generate_charts.py`                                      | `scripts/generate_charts.py` imports matplotlib                                               |
| seaborn         | `tests/test_generate_charts.py`                                      | `scripts/generate_charts.py:26` imports seaborn (surfaces only after matplotlib is installed) |

Sanity check the environment before running anything:

```bash
bash .claude/skills/eb-build-and-test/scripts/env_doctor.sh venv/bin/python
```

## 2. `make test` is broken; do not use it as a gate

`make test` runs `python3 -m pytest lib/eb_verify -q` (Makefile line 85).
As of 2026-07-07 there are **zero test files under `lib/eb_verify/`**, so it
collects nothing and exits 5 ("no tests collected"), which make reports as a
failure. It was never the CI gate even when it collected tests.

The real test tree is `tests/` at the repo root (~3,678 tests collected as of
2026-07-07). The "779+ tests across 19 test modules" figure in README.md:80
and CLAUDE.md:81 is stale.

## 3. The CI gate, and how to reproduce it locally

CI (`.github/workflows/ci.yml`, single `test` job, Python 3.12, 10-minute
timeout) runs four steps in order. A failure in one skips the rest:

```bash
# step 1: install
pip install pytest jsonschema tomli
pip install -e lib/

# step 2: tests
python3 -m pytest tests/ -v --tb=short -m "not network and not docker"

# step 3: task consistency audit (see section 7; currently cannot pass off-machine)
python3 scripts/audit_consistency.py

# step 4: shell syntax check on every non-archived benchmark script
find benchmarks -name "*.sh" -not -path "*/_archived/*" | while read f; do
  bash -n "$f" || exit 1
done
```

There is no lint or type-check step in CI. `ruff`/`mypy` caches on disk are
developer-local habits, not enforced gates.

### CI on main is red (status as of 2026-07-07)

Every one of the last 50 CI runs concluded `failure` (checked via
`gh run list`). The current failure is at step 2, **collection errors**, not
test failures: CI installs only the minimal dependency set, so
`tests/test_fact_coverage.py` and `tests/test_fact_triples_verifier.py` error
on missing numpy and `tests/test_generate_charts.py` errors on missing
matplotlib (seaborn would be next). Steps 3 and 4 are skipped, so their own
latent defects (section 7) have never surfaced in CI.

Consequences for you:

- "Is CI green after my change?" is not answerable today; the pre-existing
  red masks everything downstream of collection.
- The durable fix (add the four packages to the CI install step, or add
  `pytest.importorskip` guards) is a repo change. Treat it as gated: propose
  it through the normal review path, do not just land it.
  PROVISIONAL pending Stephanie: conservative gating per discovery Q5; CI
  workflow edits are not on the enumerated HALT list but sit adjacent to the
  scoring path, so ask first.

## 4. pytest markers

Registered in `tests/conftest.py` (`pytest_configure`): `network`, `docker`.

| Marker     | Registered? | Uses (2026-07-07) | Where                              | Effect if you run it                              |
| ---------- | ----------- | ----------------- | ---------------------------------- | ------------------------------------------------- |
| `network`  | yes         | 1                 | `tests/test_sandbox_builds.py:191` | does `git ls-remote` against real remotes         |
| `docker`   | yes         | 1                 | `tests/test_sandbox_builds.py:260` | requires a running Docker daemon, builds images   |
| `security` | **no**      | 26                | `tests/security/` (2 modules)      | runs everywhere; emits `PytestUnknownMarkWarning` |

- CI's filter `-m "not network and not docker"` deselects **8 tests**, all
  parametrized cases in `tests/test_sandbox_builds.py`.
- Running `pytest tests/` WITHOUT the filter will hit the network and try to
  use Docker. Always keep the filter unless you specifically want those tests.
- `security` tests are NOT excluded by CI; they run in the normal suite. The
  unregistered mark is warning-only because the repo does not use
  `--strict-markers`.

## 5. Collection errors: the catalog

Two distinct populations. Discriminate with `git ls-files <path>` (non-empty
output = tracked = CI sees it) before concluding anything about main.

### Tracked on main (these are what break CI)

| Module                                | Error                                            | Fix locally                      |
| ------------------------------------- | ------------------------------------------------ | -------------------------------- |
| `tests/test_fact_coverage.py`         | `ModuleNotFoundError: numpy`                     | `pip install numpy scikit-learn` |
| `tests/test_fact_triples_verifier.py` | `ModuleNotFoundError: numpy`                     | same                             |
| `tests/test_generate_charts.py`       | `ModuleNotFoundError: matplotlib` (then seaborn) | `pip install matplotlib seaborn` |

### Untracked, local working copy only (CI never sees these)

Present in the primary development working copy as of 2026-07-07; a fresh
clone of main will not have them. There are 11 untracked `.py` files under
`tests/` in total (the `env_doctor.sh` script lists them); these three are
the ones that error at collection.

| Module                                           | Error                                         | Why                                                                                                                                                                                                                                                                                                                                                                                               |
| ------------------------------------------------ | --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests/eb_metrics/test_trace_quality_adapter.py` | `ModuleNotFoundError: codeprobe`              | `lib/eb_metrics/__init__.py` imports the sibling codeprobe project (its own repo, not on PyPI). Unresolvable in a standalone clone.                                                                                                                                                                                                                                                               |
| `tests/test_verifier_mutation.py`                | `ModuleNotFoundError: verifier_mutation_test` | The module under test, `scripts/validation/verifier_mutation_test.py`, exists only on unlanded branches (added in commit `2079b2b`, "ci: wire verifier soundness gate into CI"; reachable from `fix/eb-cdzi-runner-consolidation` and others, not main). Parked, not dead: check the bead store and branch state before re-creating or deleting it. PROVISIONAL pending Stephanie (discovery Q5). |
| `tests/test_power_analysis.py`                   | `ModuleNotFoundError: numpy`                  | Both the test and `scripts/analysis/power_analysis.py` are untracked in-flight work.                                                                                                                                                                                                                                                                                                              |

To simulate a clean checkout of main without touching git state:

```bash
venv/bin/python -m pytest tests/ -q -m "not network and not docker" \
  --ignore=tests/eb_metrics \
  --ignore=tests/test_verifier_mutation.py \
  --ignore=tests/test_power_analysis.py
```

Never "fix" a collection error by deleting the test module; every one of them
points at either a missing dependency declaration or an unlanded branch.

## 6. What "green" actually looks like right now

Measured 2026-07-07, in this working copy, full dependency set installed,
CI marker filter plus the three `--ignore` flags above (runtime ~50 s):

```
357 failed, 3313 passed, 56 skipped, 8 deselected
```

Failure distribution by module: `test_support_mapping_verifiers.py` 151,
`tests/security/test_check_scripts_injection.py` 70,
`test_schema_evolution_verifiers.py` 47, `test_all_tasks_valid.py` 23,
`test_dead_code_verifiers.py` 20, `test_task_output_path_consistency.py` 19,
`test_phase4_verifiers.py` 17, `test_provenance_verifiers.py` 6,
`test_verifier_failure_class.py` 3, `test_sandbox_builds.py` 1.

Most of this red is **local in-flight work, not main**, in two forms:

- The dominant failing modules (`test_support_mapping_verifiers`,
  `test_schema_evolution_verifiers`, `test_all_tasks_valid`, ...) are tracked
  tests, but they parametrize over `benchmarks/` task data, and the failing
  task directories (e.g.
  `benchmarks/customer_escalation/support-mapping-dual-*`) are untracked.
  Example verified failure mode: 23 untracked check scripts lack the
  executable bit, exactly what
  `test_all_tasks_valid.py::test_check_scripts_exist_and_executable` asserts.
- Two failing modules (`test_task_output_path_consistency.py` 19,
  `test_verifier_failure_class.py` 3) are themselves untracked test files.

Whether tracked main is green past collection is **unknown**; CI has never
gotten past the collection errors, so nobody has a trustworthy main baseline.

Working discipline until CI is fixed:

1. Record a baseline before your change:
   `pytest tests/ -q -m "not network and not docker" <ignores> > /tmp/before.txt`
2. Make your change; rerun into `/tmp/after.txt`.
3. Diff the `FAILED` lines. Your gate is "no new failures", not "all green".
4. Before blaming main for any failure, check `git ls-files` on the failing
   test AND on the task/fixture data it reads.

## 7. `scripts/audit_consistency.py` (CI step 3)

Audits every active task for six consistency rules: (1) `python3 -c` blocks
use `os.environ`, not shell `'$VAR'` expansion; (2) scripts set
`set -euo pipefail` or `set -uo pipefail`; (3) scripts emit JSON with `score`
and `passed` keys; (4) checkpoint weights sum to 1.0 (±0.01); (5) check
scripts are chmod +x; (6) artifact types in `task.toml` match what check
scripts read. Exits 1 if any violation is found, so it is a real merge
blocker once reachable. It also writes a report to
`results/analysis/consistency_audit.md`.

**Known defect (verified 2026-07-07):** it hardcodes
`BENCH_DIR = Path("/home/ds/EnterpriseBench/benchmarks")` and a matching
`RESULTS_FILE` (lines 31-32). Unless the repo happens to live at exactly that
path, the script crashes with `FileNotFoundError` before auditing anything
(verified 2026-07-07: it crashes in the primary development working copy, and
CI runners have no `/home/ds` at all). CI
has never reached this step (step 2 fails first), which is why the defect has
not surfaced. The repo already contains the correct mechanism: the same
`scripts/lib/tasks.py::find_task_dirs` the audit calls defaults to a
`__file__`-relative `benchmarks/` path, but the audit overrides that default
with the hardcoded constant.

Fixing it is a small, gated repo change (make `BENCH_DIR`/`RESULTS_FILE`
`__file__`-relative). Until then, running it as-is fails everywhere except a
machine with the repo at exactly `/home/ds/EnterpriseBench`.

## 8. Shell-script validation (CI step 4)

```bash
find benchmarks -name "*.sh" -not -path "*/_archived/*" -exec bash -n {} \;
```

603 scripts in scope as of 2026-07-07; all pass `bash -n` today. This is
syntax-only (`bash -n` parses, never executes). Note the delta with section
6: a script can be syntactically valid yet fail the exec-bit or JSON-output
rules checked by pytest and the consistency audit.

## 9. The fact_triples optional-dependency gap

`lib/eb_verify/plugins/__init__.py` registers 9 validators unconditionally:
`answer`, `call_graph`, `code_patch`, `config`, `incident_report`,
`reproduction_script`, `runbook`, `security_assessment`,
`topological_order`. (Registry key for the config validator is `config`, not
`config_validator`.)

The 10th, `fact_triples`, is registered inside a `try/except ImportError`
(plugins/**init**.py lines ~108-124) because it needs numpy, scikit-learn,
and jsonschema, which minimal task sandboxes do not ship. When the deps are
absent:

- importing `eb_verify` emits
  `RuntimeWarning: fact_triples validator unavailable (missing dependency: ...)`
  and continues;
- `get_validator("fact_triples")` returns `None`;
- `lib/eb_verify/runner.py` (line ~292) then marks the artifact
  `valid: False` with detail `"No validator registered for type: fact_triples"`.

So the failure is explicit per-artifact, not a crash, but a dependency-free
environment scores every `fact_triples` artifact as invalid. Any task whose
`task.toml` requires the `fact_triples` artifact type (it is a legal value,
`schemas/task.schema.json:200`) silently loses that credit in such an
environment. Before trusting any run that involves fact_triples, verify the
scoring environment had the full stack:

```bash
python -c "from eb_verify.plugins import list_validators; print(sorted(list_validators()))"
# 10 entries including 'fact_triples' = full stack; 9 = degraded
```

The `env_doctor.sh` script in this skill's `scripts/` dir performs this check
among others.

## 10. Quick reference: full local setup, end to end

```bash
cd <repo-root>
python3 -m venv venv
venv/bin/pip install pytest jsonschema tomli numpy scikit-learn matplotlib seaborn
venv/bin/pip install -e lib/
bash .claude/skills/eb-build-and-test/scripts/env_doctor.sh venv/bin/python
venv/bin/python -m pytest tests/ -q -m "not network and not docker" \
  --ignore=tests/eb_metrics \
  --ignore=tests/test_verifier_mutation.py \
  --ignore=tests/test_power_analysis.py
```

Expect a nonzero failure count (section 6); gate on the before/after diff.

## Provenance and maintenance

Authored 2026-07-07 against the working copy at origin `sjarmak/EnterpriseBench`,
main @ `7cfb8b0`. Every command above was executed this session. Volatile
facts and their one-line re-verification commands:

| Fact                                     | Re-verify with                                                                                                                 |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| CI steps and marker filter               | `cat .github/workflows/ci.yml`                                                                                                 |
| `make test` target definition            | `grep -A2 '^test:' Makefile`                                                                                                   |
| `make test` collects nothing             | `venv/bin/python -m pytest lib/eb_verify -q; echo $?` (expect exit 5)                                                          |
| CI red streak on main                    | `gh run list --workflow CI --limit 10 --json conclusion,headBranch`                                                            |
| Latest CI failure cause                  | `gh run view <id> --log-failed \| grep ModuleNotFoundError`                                                                    |
| Registered markers                       | `grep addinivalue_line tests/conftest.py`                                                                                      |
| Marker usage counts                      | `grep -rho "pytest.mark.[a-z_]*" tests/ \| sort \| uniq -c`                                                                    |
| Tests deselected by CI filter            | `venv/bin/python -m pytest tests/ --collect-only -q -m "not network and not docker" \| tail -1`                                |
| Which failing tests are tracked          | `git ls-files tests/ \| grep <module>`                                                                                         |
| verifier_mutation_test still branch-only | `git log --all --oneline --diff-filter=A -- "*verifier_mutation_test*"` and `git ls-tree main --name-only scripts/validation/` |
| fact_triples conditional registration    | `sed -n '105,125p' lib/eb_verify/plugins/__init__.py`                                                                          |
| Validator registry contents              | `venv/bin/python -c "from eb_verify.plugins import list_validators; print(sorted(list_validators()))"`                         |
| audit_consistency hardcoded path         | `grep -n BENCH_DIR scripts/audit_consistency.py`                                                                               |
| Non-archived shell script count / syntax | `find benchmarks -name "*.sh" -not -path "*/_archived/*" \| wc -l` and `... -exec bash -n {} \;`                               |
| Collected test count                     | `venv/bin/python -m pytest tests/ --collect-only -q <ignores> \| tail -1`                                                      |
| Stale "779+" doc claim                   | `grep -n 779 README.md CLAUDE.md`                                                                                              |
