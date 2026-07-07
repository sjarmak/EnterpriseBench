---
name: eb-verification-library
description: >
  Architecture and runbook for lib/eb_verify — EnterpriseBench's centralized
  artifact-verification library. Load this when: working on any file under
  lib/eb_verify/; adding, modifying, or debugging an artifact validator
  (answer, code_patch, config, incident_report, runbook, security_assessment,
  reproduction_script, topological_order, call_graph, fact_triples); you see
  "No validator registered for type", the "fact_triples validator unavailable"
  RuntimeWarning, "ungrounded citations", "path escapes workspace", or
  FileTooLargeError; you need to understand safe_read/TOCTOU hardening, the
  groundedness (evidence-span citation) gate, fact_triples/fact_coverage
  scoring, or the ArtifactValidator plugin registry; or you are writing a
  checkpoint check script that imports eb_verify inside the sandbox.
---

# eb-verification-library: the `lib/eb_verify` artifact-validation axis

Verified against the repo at commit `7cfb8b0` (2026-07-06). Line numbers and
counts below are current as of 2026-07-07; re-verify with the commands in
"Provenance and maintenance" before trusting anything volatile.

## Scope — when to use this skill, and when not to

EnterpriseBench verification has two axes. This skill covers **axis (b)
only**:

- (a) **Checkpoint scoring** — bash verifier scripts printing
  `{"score": 0-1}`, weights, the Tier-2 LLM-judge `min(grep, judge)` cap,
  and _where the recorded number actually comes from_. That is
  **eb-checkpoint-scoring**. Do not learn scoring flow from this file.
- (b) **Artifact validation** — the `lib/eb_verify` plugin library that
  checks the _artifacts_ an agent produced (answer.json, git diffs, reports,
  scripts, fact triples). This file.

Use a sibling instead when:

| You need                                                           | Load                          |
| ------------------------------------------------------------------ | ----------------------------- |
| Which scorer produces the recorded number; weights; judge cap      | eb-checkpoint-scoring         |
| The non-negotiable rule about `verifier_infra_error` vs silent 0.0 | eb-scoring-integrity-doctrine |
| Writing/fixing a `task.toml`, checkpoints, expected_solution.json  | eb-task-authoring             |
| Docker sandbox lifecycle, docker-cp mechanics, chown gates         | eb-sandbox-execution          |
| Running the test suite / CI parity                                 | eb-build-and-test             |
| The scorer_guard consolidation campaign                            | eb-scorer-guard-campaign      |
| First session in this repo                                         | eb-orientation                |

**Discipline rule (PROVISIONAL pending Stephanie, per Q5):** `lib/eb_verify`
is on the production scoring path — its verdicts feed recorded benchmark
scores. Treat every behavior-changing edit here as HALT-branch-ready:
build the change on a branch with tests in the same commit, and stop for
maintainer sign-off before it lands. Nothing in this skill authorizes
landing a scoring-behavior change directly.

## 1. Package map

```
lib/
├── pyproject.toml            # package "eb-verify" v0.2.0; deps: tomli(<3.11), jsonschema
├── eb_verify/
│   ├── __init__.py           # exports TaskDefinition, parse_task, CheckpointRunner,
│   │                         #   compute_score, write_reward
│   ├── __main__.py           # `python -m eb_verify <cmd>` → cli.main()
│   ├── cli.py                # run | check | validate | validate-artifact
│   ├── task_parser.py        # task.toml → frozen TaskDefinition dataclasses
│   ├── schema_validator.py   # 2-layer task.toml validation (JSON Schema + semantic)
│   ├── runner.py             # CheckpointRunner (library scorer — see eb-checkpoint-scoring)
│   ├── scoring.py            # CheckpointResult, VerificationResult, compute_score, write_reward
│   ├── groundedness.py       # evidence-span citation gate (deterministic)
│   ├── fact_coverage.py      # TF-IDF semantic recall of GT facts (cooperative only)
│   ├── fact_coverage_calibration.py  # threshold sweep that set DEFAULT_THRESHOLD=0.40
│   ├── plugins/              # THE VALIDATOR REGISTRY (this skill's core)
│   │   ├── __init__.py       # registry, ArtifactValidator protocol, safe_read
│   │   ├── answer.py         # + oracle matching helpers
│   │   ├── call_graph.py     # dead-code claims, precision-weighted F-score
│   │   ├── code_patch.py     # git-diff presence/size/applies checks
│   │   ├── config_validator.py
│   │   ├── fact_triples.py   # conditional 10th validator (needs numpy/sklearn)
│   │   ├── file_extraction.py# NOT a registry plugin — standalone CLI scorer
│   │   ├── incident_report.py
│   │   ├── reproduction_script.py
│   │   ├── runbook.py
│   │   ├── security_assessment.py
│   │   └── topological_order.py
│   ├── judge/                # Tier-2 LLM judge (LLMJudge, cc:haiku default)
│   ├── parsers/              # language parser registry (python_ast, go_ast, manifests)
│   └── _vendor/benchmark_qa_core/  # DEAD: only __pycache__ remains, no .py source
│                             # (verified 2026-07-07; do not import)
└── eb_metrics/               # separate, NOT installed by `pip install -e lib/`
                              # (tests/eb_metrics/test_trace_quality_adapter.py fails
                              #  collection because of this — known, see eb-build-and-test)
```

Jargon, defined once:

- **Artifact** — a file the agent under evaluation writes into `/workspace`
  (e.g. `agent_output/answer.json`, `dead_code_report.json`, a git diff).
- **Validator / plugin** — a class with an `artifact_type` string and a
  `validate(workspace: Path) -> ValidationResult` method, registered in
  `plugins/__init__.py`.
- **Workspace** — the directory containing the task's cloned repos plus the
  agent's output. In the sandbox it is `/workspace`; in tests it is a tmpdir.
- **Groundedness** — a citation's `evidence_span` appearing verbatim
  (whitespace-normalized, case-insensitive) in the cited workspace file.
- **Ground truth (GT)** — task-author-provided expected data
  (`ground_truth.json`, `ground_truth/expected_facts.json`, …).

## 2. Setup and smoke test

`import eb_verify` fails on a bare interpreter — the package must be
installed editable (CI does exactly this):

```bash
cd /path/to/EnterpriseBench
pip install -e lib/
python3 -c "from eb_verify.plugins import list_validators; print(sorted(list_validators()))"
```

Expected with numpy+scikit-learn present (10 validators):

```
['answer', 'call_graph', 'code_patch', 'config', 'fact_triples',
 'incident_report', 'reproduction_script', 'runbook',
 'security_assessment', 'topological_order']
```

Without numpy/scikit-learn you get **9** (no `fact_triples`) plus a
`RuntimeWarning: fact_triples validator unavailable`. This is by design —
see §6. Verified 2026-07-07: the repo's checked-in `venv/` has no numpy, so
`venv/bin/python` registers 9.

CLI smoke (console script `eb-verify` is installed by the package;
`python -m eb_verify` is equivalent):

```bash
eb-verify validate benchmarks/technical_debt/refactor-orchestration-001/task.toml
eb-verify validate-artifact answer /path/to/some/workspace
eb-verify run <task.toml> --workspace <ws> --output reward.txt   # library scorer path
eb-verify check <checkpoint_name> <task.toml>
```

**Trap — `make test` collects ZERO tests.** The Makefile target runs
`pytest lib/eb_verify -q`, but there are no test files under `lib/`;
the library's tests live in the repo-root `tests/` tree (verified
2026-07-07: "no tests collected in 0.00s"). Run what CI runs:

```bash
python3 -m pytest tests/ -v --tb=short -m "not network and not docker"
```

Library-focused subset (282 tests collected 2026-07-07):

```bash
python3 -m pytest tests/test_plugins.py tests/test_groundedness.py \
  tests/test_runner.py tests/test_scoring.py tests/test_task_parser.py \
  tests/test_schema_validator.py tests/test_cli.py \
  tests/test_runner_grounded_citations.py -q
```

`tests/test_fact_triples_verifier.py` and `tests/test_fact_coverage.py`
import numpy at module level with no `importorskip` — they fail collection
outright in a numpy-less environment (verified 2026-07-07). Install
`numpy scikit-learn` before running them. Note CI's install step is
`pip install pytest jsonschema tomli` + `pip install -e lib/`, which does
NOT include numpy — whether those two modules actually pass in GitHub
Actions could not be verified from this machine (open question; check a
recent CI run before relying on it).

## 3. The plugin registry and the ArtifactValidator protocol

All in `lib/eb_verify/plugins/__init__.py`:

```python
@dataclass
class ValidationResult:
    valid: bool
    detail: str = ""

class ArtifactValidator(Protocol):
    artifact_type: str
    def validate(self, workspace: Path) -> ValidationResult: ...

register(validator)            # _registry[validator.artifact_type] = validator
get_validator(artifact_type)   # -> validator or None (NEVER raises)
list_validators()              # -> list of registered type names
```

Registration is import-time: the bottom of `plugins/__init__.py` imports the
nine always-on validator classes and calls `register(...)` on an instance of
each. There is no entry-point discovery, no config file — **the registry IS
that import block**.

Signature convention (load-bearing): the protocol is `validate(workspace)`
with **no other required parameters**. Callers (`CheckpointRunner`,
`eb-verify validate-artifact`) invoke `validator.validate(workspace)` bare.
Any extra parameter on a concrete validator MUST be keyword-with-default
(`ground_truth=None`, `require_grounded_citations=False`, …). The one
optional capability the runner knows how to forward is
`require_grounded_citations` — it probes for it with
`inspect.signature(validator.validate).parameters`
(`runner.py::CheckpointRunner.validate_artifacts`). A validator that lacks
the kwarg on a task that demands grounding is failed **explicitly** with
"does not support grounded citations" — it is never run without the gate.

`get_validator` returning `None` surfaces as an artifact result
`"No validator registered for type: X"` (valid=False), not an exception.
This is exactly what happens for `fact_triples` in a dependency-free sandbox
and for the two schema-only types in §4's table footnote.

## 4. The 9+1 validators

All classes live in `lib/eb_verify/plugins/<file>.py`. "Grounding kwarg"
means `validate()` accepts `require_grounded_citations`.

| artifact_type                | File                   | Looks for (glob in workspace)                                                                                               | Verdict logic                                                                                                                                                      | Grounding kwarg                                                     |
| ---------------------------- | ---------------------- | --------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------- |
| `answer`                     | answer.py              | `**/answer.json`, else `**/answer.txt`                                                                                      | JSON object / non-empty text; optional oracle scoring (keywords, symbols, file paths, fuzzy; weighted aggregate vs `min_score`, default 0.3)                       | yes — top-level `citations` list                                    |
| `code_patch`                 | code_patch.py          | any repo dir (`<ws>/*/.git`) with staged or unstaged diff                                                                   | valid if ≥1 repo has changes; diff-size bounds (1..10,000 lines) and optional `git apply --check` produce WARNINGS only                                            | no                                                                  |
| `config`                     | config_validator.py    | `*.yaml/yml/json/toml/hcl` in `<ws>/output`, `<ws>/artifacts`, `<ws>` top-level                                             | syntax-parses each; zero files found is VALID ("not required to exist"); yaml/toml parsing silently skipped if parser lib absent                                   | no                                                                  |
| `incident_report`            | incident_report.py     | `**/incident_report.json`, `**/incident-report.json`, `**/output/incident_report.json`, `**/artifacts/incident_report.json` | required fields `timeline, root_cause, remediation, affected_services`; section non-emptiness; timeline chronological-order check; optional cross-reference checks | yes — top-level `citations`                                         |
| `runbook`                    | runbook.py             | `**/runbook.md`, `**/RUNBOOK.md`                                                                                            | markdown headers must contain `overview`, `steps`, `rollback`                                                                                                      | no                                                                  |
| `reproduction_script`        | reproduction_script.py | `**/reproduce.*`, `**/reproduction.*`, `**/repro.*`                                                                         | exists, workspace-contained, executable bit set                                                                                                                    | no                                                                  |
| `security_assessment`        | security_assessment.py | `**/security_assessment.json`, `**/security-assessment.json`                                                                | required fields `vulnerabilities, severity_summary, recommendations`                                                                                               | yes — **per-finding** `citations` (see §6)                          |
| `topological_order`          | topological_order.py   | `ordering.json` (workspace mode)                                                                                            | fraction of pairwise dependency constraints satisfied × repo-coverage; 0.0 on cyclic graph                                                                         | no                                                                  |
| `call_graph`                 | call_graph.py          | `**/dead_code_report.json` + `ground_truth/dead_code.json`, `ground_truth/live_code.json`                                   | precision-weighted F-score (β=0.5, precision counts double); dynamic/reflection false positives discounted ×0.5; empty claim set scores 0.0                        | no                                                                  |
| `fact_triples` (conditional) | fact_triples.py        | `**/facts.json` (excluding `ground_truth/`) + `ground_truth/expected_facts.json`                                            | three-layer score, §6                                                                                                                                              | yes — accepted but a documented no-op: grounding is ALWAYS enforced |

Two library functions that are **not** registry plugins:

- `plugins/file_extraction.py` — a standalone CLI scorer for file-list
  checkpoints (`python3 -m eb_verify.plugins.file_extraction --keys ... 
--policy suffix`), reading `$ANSWER_FILE` / `$GT_FILE`. It replaced 37
  copy-pasted inline-Python check scripts after a shell-injection fix (bead
  0rv.23, per its docstring). Today only 2 task check scripts exec it
  (both under `benchmarks/customer_escalation/`); ~29 others are bash+jq
  reimplementations whose comments cite it as the reference semantics.
  Missing answer.json → zero-score JSON, exit 0 (agent failure); missing
  ground_truth.json → error JSON on stderr, exit 1 (infra failure). Keep
  that asymmetry — it is the scoring-integrity doctrine in miniature.
- `topological_order.validate_refactor_plan_markdown(plan_text, dep_graph)`
  — the single entry point `checks/check_topo_order.sh` uses across
  refactor-orchestration tasks; extracts the agent's ordering from any of
  the markdown shapes real runs produced (Step/Phase headings, numbered
  lists, `**Repo:**` fields) and delegates to `validate_topological_order`.

Footnote: `schemas/task.schema.json` allows two artifact types with **no
validator anywhere**: `kb_article` and `migration_guide`. A task declaring
them as required will fail every run with "No validator registered". Do not
use them without shipping a validator first. Also
`cli.py::cmd_validate_artifact`'s "Available types" error message lists only
7 types (stale — missing `call_graph`, `topological_order`, `fact_triples`);
trust `list_validators()`, not that string.

Artifact discovery uses `workspace.glob(...)` and takes the **first match**
(`candidates[0]`, sorted only for fact_triples). Two answer.json files in
different repos = the glob-order winner gets validated. Keep artifacts at
their canonical path (`/workspace/agent_output/answer.json`).

## 5. safe_read: containment + size hardening (TOCTOU-closed)

Every validator that reads agent-controlled files goes through
`plugins.safe_read(path, workspace, max_bytes=None)`. What it guarantees
(read the docstring at `plugins/__init__.py:57` — it is accurate):

1. Opens the path **once** via `os.open`, then derives the real path from
   `/proc/self/fd/<fd>`. Containment check, size check, and read all use
   that same fd — no resolve-then-reopen window for a symlink swap (TOCTOU
   = time-of-check-to-time-of-use).
2. Containment first: a resolved path outside `workspace` raises
   `ValueError("Path escapes workspace: ...")` and is never stat'd or read.
   This kills `../` traversal and symlink escapes from agent-written JSON.
3. `max_bytes` set → `os.fstat(fd).st_size` over the cap raises
   `FileTooLargeError` **without reading**. `MAX_ARTIFACT_BYTES = 10 MiB`
   is the cap used by `answer` and `incident_report` artifact reads;
   `groundedness.MAX_EVIDENCE_FILE_BYTES = 10 MiB` caps cited evidence
   files.

Rules when writing validator code:

- Never `path.read_text()` on anything the agent could have written or
  symlinked. Always `safe_read(path, workspace)`; pass
  `max_bytes=MAX_ARTIFACT_BYTES` for whole-file JSON/text artifact reads.
- Catch `ValueError` from safe_read and convert to
  `ValidationResult(valid=False, detail=str(e))` — an escape attempt is an
  invalid artifact, not a crash.
- Tests for this live in `tests/test_plugins.py::TestSafeReadMaxBytes` and
  the containment cases in `tests/test_groundedness.py`. Extend them if you
  touch safe_read.

## 6. The groundedness gate (`groundedness.py`)

Deterministic evidence-span checking, opt-in per task via
`[ground_truth] require_grounded_citations = true` in task.toml
(schema: `schemas/task.schema.json`, parsed into
`task_parser.GroundTruth.require_grounded_citations`; only 2 active tasks
set it as of 2026-07-07).

Data model: `Citation(repo, file, evidence_span)` — `repo` may be `""` for
single-repo tasks. `check_groundedness(citations, workspace)` returns a
`GroundednessResult` with per-citation reasons:

| reason           | meaning                                                                  |
| ---------------- | ------------------------------------------------------------------------ |
| `ok`             | span found verbatim (whitespace-collapsed, lowercased) in the cited file |
| `span_not_found` | file read fine; span absent → fabricated/paraphrased evidence            |
| `file_missing`   | cited file absent, unreadable, or binary                                 |
| `path_escape`    | safe_read containment fired (`..` or symlink escape)                     |
| `too_short`      | normalized span < `MIN_SPAN_CHARS` (20) — "import os" is not evidence    |
| `too_large`      | cited file > `MAX_EVIDENCE_FILE_BYTES` (10 MiB), rejected unread         |

Score = grounded/total; an **empty citations list scores 1.0** ("no claims
means nothing is ungrounded") — except where the artifact's convention says
otherwise (next paragraph). File contents are cached per call keyed on
`(repo, file)`; read failures are deliberately not cached.

Two citation conventions exist, on purpose:

- **Top-level `citations` list** (answer, incident_report): the artifact is
  free-form JSON, so the top level is the only stable seam. Missing or
  malformed `citations` raises `CitationParseError` → validation fails with
  per-entry issues. `answer.txt` cannot carry structured citations, so a
  txt-only workspace fails the gate explicitly.
- **Per-finding `citations`** (security_assessment): each entry in
  `vulnerabilities` must carry its own non-empty citations list. Rationale
  (from the module docstring): each finding is an independent claim, and one
  top-level grounded citation must not launder N fabricated findings. Here
  an EMPTY per-finding list FAILS (a claim with zero evidence), deliberately
  diverging from the top-level empty-list-passes rule. An empty
  `vulnerabilities` list has nothing to ground and passes.

Runner enforcement (`runner.py::run_all`): when the task requires grounding
and any required artifact fails validation, `total_score` is **forced to
0.0** and the gate is recorded in `VerificationResult.score_gates` — the
flag must never be a side channel with no score effect. Capability probing
is described in §3. Tests: `tests/test_groundedness.py`,
`tests/test_runner_grounded_citations.py`,
`tests/test_plugins.py::TestAnswerGroundedCitations` /
`TestSecurityAssessmentGroundedCitations`.

## 7. fact_triples and fact_coverage (comprehension scoring)

`fact_triples` is the conditional 10th validator: agent writes `facts.json`
(knowledge-graph triples `subject/predicate/object` + natural-language
`statement` + verbatim `evidence` span + integer `confidence` 0-100; JSON
Schema enforced in-module). Ground truth is
`workspace/ground_truth/expected_facts.json`.

Three-layer score (`score_fact_triples`):

1. **Groundedness gate** — every fact's evidence span checked via §6;
   ungrounded facts are DISCARDED before any credit (reasons recorded).
2. **Coverage/recall** — one-to-one matching of GT facts by exact canonical
   triple first, then greedy semantic fallback on `statement` similarity
   (threshold `DEFAULT_SEMANTIC_THRESHOLD = 0.5` — an uncalibrated chosen
   operating point, per the in-code comment).
3. **Precision penalty** — `score = recall * (1 - alpha * unmatched_fraction)`,
   `DEFAULT_ALPHA = 0.3`; surviving facts matching no GT fact cost you.

Validator verdict is `valid = total_score > 0.0`, with the full breakdown in
`detail`.

**Conditional registration:** `plugins/__init__.py` imports
`FactTriplesValidator` inside `try/except ImportError` because it needs
numpy + scikit-learn (via `fact_coverage`) + jsonschema, which minimal task
sandboxes do not ship. On ImportError it emits a `RuntimeWarning` and
`get_validator("fact_triples")` returns `None` — the runner then reports the
missing validator explicitly. Consequence: **a fact_triples task scored in a
dependency-free environment fails its artifact check loudly rather than
silently skipping the gate.** If you see that RuntimeWarning where you
expected fact scoring, install `numpy scikit-learn`.

`fact_coverage.py` is the underlying semantic-recall engine:
`coverage(gt_facts, candidate_facts)` = fraction of GT facts whose best
cosine similarity ≥ `DEFAULT_THRESHOLD = 0.40` (calibrated: best F1 0.828 on
the labeled pair set in `fact_coverage_calibration.py`). The default
embedder is deterministic TF-IDF over char 3-5-grams, fit per call — no
network, no state. Pluggable via the `Embedder` / `StatementSimilarity`
Protocols.

**Deployment boundary — do not move without re-verifying.** The TF-IDF
default is for **cooperative partial-credit recall only** (honest output,
missed-fact detection). The module docstring records the adversarial
verification: bag-of-ngrams is word-order-blind, so a direction-reversed
relation ("scheduler restarts the worker" vs "worker restarts the
scheduler") scores similarity 1.000 and a negated statement ~0.956. Never
wire this embedder into anything an agent could game for score. Before it
grades anything adversarial: plug in a real embedding model and re-run the
calibration sweep, or add a directional/negation post-check on matched
pairs. This boundary is repo doctrine, not a suggestion.

## 8. Who consumes the library (two callers, one trap)

1. **Library scorer** — `CheckpointRunner.run_all()` via `eb-verify run` and
   `tests/`. Weight-normalized (`scoring.compute_score` divides by total
   weight), Tier-2-capped, grounding-gated. **This is the tested reference
   path, and it is NOT what produces published run scores.**
2. **Production path** — `scripts/orchestration/run_task.py` copies
   `lib/eb_verify` into the container at `/workspace/.eb_verify` and runs
   the in-container `test.sh` (`scripts/sandbox/test_runner.sh`) with
   `PYTHONPATH=/workspace/.eb_verify`. Check scripts import the library from
   there (e.g. `check_topo_order.sh` →
   `eb_verify.plugins.topological_order.validate_refactor_plan_markdown`;
   two tasks exec `python3 -m eb_verify.plugins.file_extraction`).
   test_runner.sh reads per-checkpoint weight from a `.meta` sidecar that
   run_task.py at HEAD `7cfb8b0` never emits (default weight 1.0) and does
   not normalize its sum. Volatile: the fetched `origin/main` DOES emit
   `.meta` sidecars — the full divergence story and the stale-on-pull
   warning are eb-checkpoint-scoring's territory (§1–§3).

**PROVISIONAL pending Stephanie (Q3):** whether the two paths consolidate,
the library stays a CI oracle, or `.meta` weight-propagation lands is an
open decision. Until it is made: a scoring-behavior change made ONLY in
`CheckpointRunner`/`scoring.py` does not reach production runs, and a change
made only in `test_runner.sh` is untested by the library suite. When you
change validator behavior, check both consumers and say so in the PR.

The docker-cp trap (fixed, do not regress): `docker cp SRC_DIR DEST` where
DEST does not exist copies SRC's _contents_, dropping the `eb_verify`
package directory and breaking `python3 -m eb_verify...` under PYTHONPATH.
The `mkdir -p /workspace/.eb_verify` before the copy in
`run_task.py::_setup_container` (run_task.py:564) is **load-bearing** — the in-code comment
documents the incident (silent 0.0s from ModuleNotFoundError). Details in
eb-sandbox-execution.

Known weak point, open as of 2026-07-07 (from the 2026-07-06 self-audit;
fix candidates live on branches, not `main`): `code_patch.py`'s
`_get_diff_stat`/`_get_diff_lines` catch `(subprocess.TimeoutExpired,
Exception)` and return `None`/`0`, so a git failure inside a repo is
indistinguishable from "no changes" → a false "No code changes detected"
invalid verdict instead of an infra error. If your work touches code_patch,
read eb-scoring-integrity-doctrine first and do not replicate the pattern.

## 9. Checklist — adding a new artifact validator

Follow in order. Everything is on the production scoring path (see the
PROVISIONAL discipline rule in Scope).

1. **Confirm no existing validator covers it.** `list_validators()` + read
   the §4 table. Prefer extending an existing validator's optional kwargs
   over a near-duplicate type (rule of three).
2. **Write the failing tests first** in `tests/test_plugins.py` (one
   `Test<Name>Validator` class; mirror `TestRunbookValidator` for a simple
   shape, `TestSecurityAssessmentGroundedCitations` if you support
   grounding). Cover: missing artifact → invalid; malformed → invalid with
   precise detail; happy path; containment (symlink/`..` escape rejected);
   oversized file if you read whole files.
3. **Create `lib/eb_verify/plugins/<type>.py`**:
   - Class with `artifact_type = "<type>"` and
     `validate(self, workspace: Path, ...) -> ValidationResult`; every extra
     parameter keyword-with-default (§3 signature convention).
   - All agent-file reads via `safe_read(..., workspace, max_bytes=MAX_ARTIFACT_BYTES)`;
     convert `ValueError` → invalid result (§5).
   - Failure verdicts carry an actionable `detail` (name the file, the
     field, the reason). Never `except: return ValidationResult(False)`
     without detail, and never swallow an _infrastructure_ failure into a
     plausible-looking agent failure — that is the repo's dominant
     historical bug class (eb-scoring-integrity-doctrine).
   - Module docstring states the artifact contract (path, JSON shape) and,
     if you support grounding, WHICH citation convention (§6) and why.
   - Heavy deps → follow the fact_triples pattern: import guarded in
     `plugins/__init__.py`, RuntimeWarning on absence, never a hard crash.
4. **Register it** in `plugins/__init__.py`: import + `register(<Class>())`
   in the always-on block (or the guarded block for heavy deps).
5. **Add the type to the schema enum** —
   `schemas/task.schema.json` → `properties.artifacts...required.items.enum`.
   Without this, task authors cannot declare it and `eb-verify validate`
   rejects their task.toml. (This is also where `kb_article` /
   `migration_guide` sit validator-less today — do not add enum entries
   without validators again.)
6. **Grounding decision:** if the artifact makes claims about code, decide
   top-level vs per-claim citations (§6) and accept
   `require_grounded_citations`; otherwise omit the kwarg and the runner's
   probe will correctly refuse to pair your type with a grounding task.
7. **Update the stale CLI list** in `cli.py::cmd_validate_artifact` (or fix
   it to print `list_validators()` — net-negative diff preferred).
8. **Verify both consumers (§8):** run the library tests AND check whether
   any in-container check script should call your validator; if yes, test
   under `PYTHONPATH=<repo>/lib python3 -m ...` the way the sandbox does.
9. **Run the CI gate locally** (not `make test`):
   `python3 -m pytest tests/ -m "not network and not docker" -q` and
   `python3 scripts/audit_consistency.py`.
10. **Docs:** CLAUDE.md and docs/ARCHITECTURE.md both state the validator
    count ("9 artifact validators") — update the count and the list, or the
    next consistency audit flags the drift.
11. **Ship tests with the change, on a branch, and HALT for review**
    (PROVISIONAL per Q5, see Scope).

## Provenance and maintenance

Authored 2026-07-07 against commit `7cfb8b0` by the retiring-fellow campaign
(Phase 2). Positions marked PROVISIONAL depend on the Phase-1 discovery
report's provisional answers to Q3 (two-scorer future) and Q5 (HALT gating
scope) and are revisable by Stephanie's real answers.

Re-verify volatile facts (run from the repo root):

```bash
# Registered validators (expect 9, or 10 with numpy+sklearn)
python3 -c "from eb_verify.plugins import list_validators; print(sorted(list_validators()))"

# Registry + safe_read still live in plugins/__init__.py
grep -n "def safe_read\|MAX_ARTIFACT_BYTES\|^register(" lib/eb_verify/plugins/__init__.py

# Which validators accept the grounding kwarg (expect: answer, fact_triples,
# incident_report, security_assessment)
grep -rln "require_grounded_citations" lib/eb_verify/plugins/*.py

# Groundedness constants
grep -n "MIN_SPAN_CHARS\|MAX_EVIDENCE_FILE_BYTES" lib/eb_verify/groundedness.py

# fact scoring constants (alpha, thresholds)
grep -n "DEFAULT_ALPHA\|DEFAULT_SEMANTIC_THRESHOLD" lib/eb_verify/plugins/fact_triples.py
grep -n "DEFAULT_THRESHOLD" lib/eb_verify/fact_coverage.py

# Schema enum vs registry drift (kb_article/migration_guide still validator-less?)
python3 - <<'EOF'
import json; enum=json.load(open("schemas/task.schema.json"))["properties"]["artifacts"]["properties"]["required"]["items"]["enum"]
from eb_verify.plugins import list_validators; print(sorted(set(enum)-set(list_validators())))
EOF

# make test still collects nothing from lib/ (trap in §2 still true?)
python3 -m pytest lib/eb_verify -q --collect-only | tail -1

# Production consumption points still as described
grep -n "mkdir.*\.eb_verify\|PYTHONPATH=/workspace/.eb_verify" scripts/orchestration/run_task.py
grep -rln "eb_verify" benchmarks --include="*.sh" | grep -v _archived

# code_patch known-weak-point still open on main?
grep -n "except (subprocess.TimeoutExpired, Exception)" lib/eb_verify/plugins/code_patch.py

# Tasks currently opting into the groundedness gate
grep -rln "require_grounded_citations" benchmarks --include="task.toml" | grep -v _archived
```
