---
name: eb-task-authoring
description: >
  Authoring and fixing EnterpriseBench benchmark tasks. Load this skill when
  adding a new task under benchmarks/, editing an existing task.toml, writing
  or debugging checkpoint verifier scripts in checks/, choosing a
  difficulty_stratum, creating or curating expected_solution.json, enabling
  the grounded-citation gate (require_grounded_citations), or running the
  task validation gates (make verify, verify-mix, verify-tasks, verify-crnt,
  validate_tasks_preflight.py, validate_expected_solutions.py,
  audit_consistency.py). Also load it when a task fails schema validation,
  checkpoint weights don't sum to 1.0, or a verifier script is rejected by
  the consistency audit.
---

# eb-task-authoring — adding and fixing benchmark tasks

All facts below were verified against the repo working tree on **2026-07-07**.
Re-verification one-liners are in "Provenance and maintenance" at the end.

## When NOT to use this skill

| You are doing…                                                                          | Use instead                                   |
| --------------------------------------------------------------------------------------- | --------------------------------------------- |
| Learning what EnterpriseBench is, suite/type taxonomy, repo layout                      | `eb-orientation`                              |
| Understanding how checkpoint scores become a task score, the two scorers, LLM-judge cap | `eb-checkpoint-scoring`                       |
| Deep CRNT theory and PRD task-mix targets, ecosystem caps                               | `eb-crnt-and-task-mix`                        |
| Adding/altering an artifact validator in `lib/eb_verify/plugins/`                       | `eb-verification-library`                     |
| Running a task in its Docker sandbox, debugging container issues                        | `eb-sandbox-execution`                        |
| baseline / mcp_only / hybrid modes, MCP preflight                                       | `eb-mcp-modes`                                |
| Provisioning sg-evals mirrors, `sg_indexing_list.json`                                  | `eb-sourcegraph-mirrors`                      |
| Local env setup, pytest markers, CI vs `make test`                                      | `eb-build-and-test`                           |
| Any change to the scoring path itself                                                   | `eb-scoring-integrity-doctrine` first, always |

**Jargon used once, defined once:**

- **Task** — one benchmark unit: a directory under `benchmarks/<suite>/<task-id>/`.
- **Checkpoint** — one graded sub-goal of a task, scored by a bash verifier script.
- **Verifier** — a shell script in the task's `checks/` dir that prints a JSON score.
- **CRNT** — Cross-Repo Necessity Test: structural proof that a multi-repo task
  actually needs every repo it declares.
- **Stratum** — the task-mix bucket (`difficulty_stratum`) used for benchmark
  distribution targets, distinct from per-task `difficulty`.

## Change control

Task edits change what the benchmark measures. Treat **task-mix changes, repo
repins, and grading-keyword relaxations as HALT-branch-ready** — stop at a
ready branch, ship tests with the change, and get maintainer (Stephanie)
sign-off before merge, the same as production-scoring-path changes.
_(PROVISIONAL pending Stephanie — conservative gating position, discovery Q5.)_

Retired tasks (`benchmarks/_archived/`, 28 single-repo tasks) and previously
cut tasks are **parked, not dead**: before re-landing or duplicating one,
check the bead store and in-flight `fix/eb-*` branches.
_(PROVISIONAL pending Stephanie — discovery Q5.)_

## 1. Task anatomy

Every active task is a directory `benchmarks/<suite>/<task-id>/`. Verified
layout (example: `benchmarks/customer_escalation/err-provenance-tri-httpx-socks-001/`):

```
task.toml               # definition; validated against schemas/task.schema.json
instruction.md          # the prompt the agent actually receives (with appendix added at run time)
ground_truth.json       # provenance data consumed by verifiers
expected_solution.json  # LLM-judge reference (per-checkpoint); 173/180 active tasks have one (2026-07-07)
checks/                 # one check_<checkpoint_name>.sh per checkpoint
environment/            # Dockerfile, Dockerfile.hybrid, Dockerfile.sg_only (95/180 tasks; preflight WARNS if absent)
instruction_mcp.md      # optional; appended in mcp_only/hybrid modes
```

Reference templates (checked in, schema-conformant):

- `benchmarks/EXAMPLE_TASK.toml` — single-session two-repo task, all sections.
- `benchmarks/EXAMPLE_CHAIN_TASK.toml` — `session_type = "chain"` variant.

Prose walkthrough: `docs/TASK_AUTHORING_GUIDE.md`. **Where the guide and
`schemas/task.schema.json` disagree, the schema wins** — known drift as of
2026-07-07:

- Guide comment says `difficulty` allows `easy`; schema enum is
  `medium | hard | expert` only.
- Guide comment says `ground_truth.tiers` allows `llm_curator|solve_verification`;
  schema enum is `deterministic | curator | solve_verified`.

As of 2026-07-07 there are **180 active tasks in the working tree**
(`_archived/` and `mined/` excluded) — but only **116 of them are tracked at
HEAD `7cfb8b0`**; 64 are uncommitted working-tree additions. A public clone
sees 116, not 180 (verify:
`git ls-tree -r HEAD --name-only benchmarks/ | grep 'task.toml$' | grep -vc _archived`
vs `find benchmarks -name task.toml -not -path '*_archived*' | wc -l`).
The 112 figure in `CLAUDE.md`/README is stale either way.

## 2. task.toml reference (verified against schemas/task.schema.json)

Top-level required tables: `task`, `repos`, `checkpoints`, `artifacts`.
Preflight additionally requires the top-level scalars
`difficulty_stratum`, `mcp_suite`, `verification_modes`
(`scripts/validate_tasks_preflight.py`, `EXPECTED_TOP_LEVEL`). TOML rule:
these scalars must appear **before** the first `[section]` header.

```toml
difficulty_stratum = "dual_repo"      # see §4
mcp_suite = "eb_v1"                   # only allowed value today
repo_set_id = "kubernetes-ecosystem"  # pattern ^[a-z][a-z0-9-]+$
org_scale = true
verification_modes = ["deterministic"]  # deterministic|llm_curator|solve_verified|structural_match
```

### [task]

Required: `id`, `suite`, `difficulty`, `session_type`.

| Field                        | Constraint (schema)                                                                                                                                      |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `id`                         | pattern `^[a-z][a-z0-9-]+-\d{3}$`, must equal `task_id` in expected_solution.json                                                                        |
| `suite`                      | one of the 7: dependency_management, incident_response, platform_engineering, security_operations, customer_escalation, feature_delivery, technical_debt |
| `difficulty`                 | `medium` \| `hard` \| `expert` (NO `easy`)                                                                                                               |
| `session_type`               | `single` \| `chain` \| `event_replay` \| `resume`                                                                                                        |
| `session_count`              | 1–10, chain only                                                                                                                                         |
| `estimated_duration_minutes` | 5–480                                                                                                                                                    |
| `task_type`                  | one of the 10 types; not schema-required, but the mix validator counts by it — always set it                                                             |
| `prompt`                     | metadata; the agent is shown `instruction.md`, not this field (verified: `run_task.py::_build_instruction_text` reads only `instruction.md`)             |

### [[repos]] (1–5 entries)

Required per entry: `url`, `rev`, `path`. `role` enum:
`primary | dependency | consumer | upstream | intermediary | deprecated_upstream`.
Repos are cloned to `/workspace/<path>/` in the sandbox. Pin `rev` to a tag or
SHA; repins are change-controlled (see above) and tracked in
`configs/repo_versions.json`.

### [[checkpoints]] (1–5 entries)

Required per entry: `name`, `weight`, `verifier`. Optional: `description`,
`timeout_seconds` (default 120), `repo_deps` (per-checkpoint repo anchoring
for CRNT).

Rules that gate merges:

- **Weights must sum to 1.0 ± 0.01** — preflight `error`, CI test
  (`tests/test_all_tasks_valid.py::test_checkpoint_weights_sum`), and
  `audit_consistency.py` all check it.
- `verifier` is a path relative to the task dir; the file must exist
  (preflight `error`) and be executable (preflight `warning`, audit check).
- **Name the file `checks/check_<checkpoint_name>.sh`.** Production copies
  `checks/*.sh` to `/workspace/.verifiers/` with the `check_` prefix
  stripped, and checkpoint identity in the container is the stripped
  filename — not the `name` field (verified: `run_task.py` copy loop +
  `scripts/sandbox/test_runner.sh` single-checkpoint mode).
- **Production runs every `.sh` in `checks/`**, whether or not it is declared
  as a checkpoint — `test_runner.sh` iterates `/workspace/.verifiers/*.sh`.
  Don't leave helper scripts in `checks/`.
- **Whether `weight` and `timeout_seconds` are honored at run time is a
  volatile scoring fact owned by eb-checkpoint-scoring §1–§3** (at HEAD
  `7cfb8b0` production is equal-weighted; the already-fetched `origin/main`
  writes `.meta` weight sidecars and honors declared weights — read the
  stale-on-pull warning there before relying on either). Author weights
  correctly regardless; do not write tasks whose scoring depends on one
  behavior. _(PROVISIONAL pending Stephanie — discovery Q3.)_

### [artifacts]

`required` / `optional` lists from the enum: `code_patch`, `config`,
`incident_report`, `runbook`, `reproduction_script`, `kb_article`,
`security_assessment`, `migration_guide`, `answer`, `topological_order`,
`call_graph`, `fact_triples`. Each required artifact must have a registered
validator in `lib/eb_verify/plugins/` or it scores invalid at run time
("No validator registered"). `audit_consistency.py` checks that artifact
types match what your check scripts read.

### [tool_access]

`expected_mcp_benefit` (`high|medium|low` — schema has no `none` despite the
guide example) plus `mcp_benefit_rationale` (why MCP helps or doesn't).
Optional `[[tool_access.sourcegraph_mirrors]]` entries — mirror provisioning
is `eb-sourcegraph-mirrors`' territory.

### [ground_truth]

- `tiers`: subset of `deterministic | curator | solve_verified`.
- `[[ground_truth.required_files]]`: required per entry `path`, `repo`
  (`repo` must match a `repos[].path`); optional `line_range`, `confidence`
  (0–1), `source` (`deterministic|curator|both`). Missing these files in an
  agent's answer = significant penalty; they are also what CRNT counts.
- `[[ground_truth.sufficient_files]]`: same shape, small penalty.
- `require_grounded_citations = true`: the grounded-citation opt-in, §6.

### [csb_lineage], [events], [resume_state]

`csb_lineage` records CodeScaleBench provenance for migrated tasks.
`events` only for `session_type = "event_replay"`; `resume_state` only for
`resume` (note: `resume` is currently accepted but skipped by the
orchestrator — see `eb-session-types`).

## 3. Checkpoints as bash verifiers

### The output contract (schemas/verifier_output.schema.json)

Print ONE JSON object to **stdout**. Required keys: `score` (0.0–1.0) and
`passed` (bool). Optional: `detail` (string), `evidence` (array). Fallback
if stdout is not JSON: exit 0 ⇒ `{score: 1.0, passed: true}`, nonzero ⇒
`{score: 0.0, passed: false}`. Don't rely on the fallback — always print
JSON and `exit 0`, reporting failures inside the JSON.

Runtime facts (verified in `scripts/sandbox/test_runner.sh`):

- Verifiers run as `bash <script>` under `timeout` (124 ⇒ scored 0.0
  "Timed out").
- `WORKSPACE` is **not exported** to your script — write
  `${WORKSPACE:-/workspace}` so the fallback applies in-container and the
  variable can be injected in local testing.
- stdout is parsed as JSON only if it starts with `{` — keep diagnostics on
  stderr.
- The eb_verify library is staged at `/workspace/.eb_verify`; check scripts
  that need it use `PYTHONPATH=/workspace/.eb_verify python3 -m eb_verify...`.

### Template (matches the checked-in guide and audit rules)

```bash
#!/usr/bin/env bash
# Checkpoint: <what this verifies>
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/repo-name/IMPACT_REPORT.md"

if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "IMPACT_REPORT.md not found"}\n'
  exit 0
fi

FOUND=0; TOTAL=2
if grep -qiE 'package-a' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'package-b' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge "$TOTAL" ]; then PASSED=true; else PASSED=false; fi
printf '{"score": %s, "passed": %s, "reason": "Found %d/%d items"}\n' \
  "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
```

### Hygiene rules enforced by `scripts/audit_consistency.py` (CI step)

1. `set -euo pipefail` (or `set -uo pipefail`) at the top.
2. In embedded `python3 -c` blocks, read env via `os.environ`, never `'$VAR'`
   shell interpolation (command-injection surface).
3. Output JSON contains `score` and `passed` keys.
4. Checkpoint weights sum to 1.0 (±0.01).
5. `chmod +x` every check script.
6. Artifact types read by scripts match `[artifacts]` in task.toml.

Plus from `docs/TASK_AUTHORING_GUIDE.md` (Security Patterns): quote every
variable, use heredocs for multi-line content, and containment-check any
path you `realpath` before reading it.

**Grading-keyword lists inside verifiers are scoring policy.** Relaxing a
grep pattern changes scores across published runs — that is a
change-controlled edit (see Change control) and a scoring-integrity concern
(`eb-scoring-integrity-doctrine`).

### CI also syntax-checks every script

`.github/workflows/ci.yml` runs `bash -n` on every non-archived
`benchmarks/**/*.sh`. Run it yourself before pushing:

```bash
find benchmarks -name "*.sh" -not -path "*/_archived/*" -exec bash -n {} \;
```

## 4. Difficulty strata

`difficulty_stratum` enum (schema): `calibration`, `large_single`,
`dual_repo`, `tri_repo`, `multi_repo`, `monorepo_cross_package`.

Active distribution, counted 2026-07-07 (180 working-tree tasks; only 116
are tracked at HEAD — on a public clone every count below is smaller;
re-run `python3 scripts/validation/task_mix_validator.py`, don't quote):

| Stratum                | Count |
| ---------------------- | ----- |
| calibration            | 14    |
| large_single           | 25    |
| dual_repo              | 94    |
| tri_repo               | 21    |
| multi_repo             | 14    |
| monorepo_cross_package | 12    |

The **enforced** targets live in `scripts/validation/task_mix_validator.py`
(`make verify-mix`), not in the schema's description string (which carries a
stale 15/25/30/20/10 breakdown):

- strict multi-repo (`dual_repo`+`tri_repo`+`multi_repo`) ≥ 45% of all tasks
  (currently 71.7%, PASS);
- every one of the 10 task types has ≥ 2 multi-repo variants;
- no single ecosystem > 40% of multi-repo tasks (currently `go` at 39.7% —
  **adding one more Go multi-repo task can flip this gate to FAIL**; check
  before you pick repos).

`calibration` and `large_single`/`monorepo_cross_package` strata are
excluded from LLM-curator batch enablement (see §5). Deeper mix/CRNT theory:
`eb-crnt-and-task-mix`.

## 5. expected_solution.json

One file per task, next to task.toml. It is the reference the LLM judge
scores against (library: `lib/eb_verify/runner.py`; production:
`run_task.py::_apply_llm_judge`, active when `verification_modes` includes
`llm_curator`). Contract (`schemas/expected_solution.schema.json`,
`additionalProperties: false`):

```json
{
  "task_id": "err-provenance-tri-httpx-socks-001",
  "checkpoints": {
    "origin_and_grammar": {
      "expected_solution": "Long-form prose, function-level and file-path-specific…",
      "evaluation_criteria": [
        "Names h11/h11/_readers.py as the origin of 'illegal header line'",
        "Identifies the compiled header grammar regex in h11/h11/_abnf.py"
      ]
    }
  }
}
```

Rules enforced by `scripts/validation/validate_expected_solutions.py`:

- **C1**: every `[[checkpoints]].name` in task.toml has a key here — keys
  must match exactly; extra or missing keys are errors.
- `evaluation_criteria` ≥ 2 entries; checkpoints with weight > 0.30 want ≥ 3
  (**H3**, warning only).
- **H2**: any `"_curation_required": true` fails validation — that flag is
  what the scaffolder leaves on checkpoints it could not draft; hand-curate
  and delete it.
- **H1** (opt-in `--check-paths`, needs `GITHUB_TOKEN`): path-like strings in
  criteria must exist at the pinned repo SHA.

Workflow:

```bash
# 1. Draft mechanically (prints to stdout; --write creates the file, --force overwrites)
python3 scripts/validation/scaffold_expected_solution.py benchmarks/<suite>/<task-id> --write
# 2. Hand-curate: replace stubs, remove any _curation_required flags
# 3. Validate (the path argument is REQUIRED — a bare invocation exits 2)
python3 scripts/validation/validate_expected_solutions.py benchmarks/<suite>/<task-id>
python3 scripts/validation/validate_expected_solutions.py benchmarks/   # whole tree
# 4. (multi-repo strata only) flip verification_modes to include llm_curator
python3 scripts/validation/enable_llm_curator.py benchmarks/ --dry-run
```

`enable_llm_curator.py` eligibility: stratum is dual/tri/multi-repo AND a
sibling expected_solution.json exists; it does a conservative textual
replacement of the canonical line `verification_modes = ["deterministic"]`.

173 of the 180 working-tree active tasks have expected_solution.json
(2026-07-07; working-tree census — a public clone at HEAD sees fewer, see
§1).

## 6. Grounded-citation opt-in

Purpose: force the agent to prove each claim with a verbatim quote from a
workspace file, killing paraphrase/fabrication credit. Deterministic gate,
no LLM involved (`lib/eb_verify/groundedness.py`).

Opt in per task:

```toml
[ground_truth]
tiers = ["deterministic", "curator"]
require_grounded_citations = true
```

What flips on (all verified in source):

1. **Instruction appendix** — `run_task.py::_build_instruction_text` adds a
   required top-level `citations` block to the answer.json format appendix,
   so the agent is told the contract.
2. **Answer shape** — `agent_output/answer.json` must carry a top-level
   `citations` list; each entry
   `{"repo": "<repos[].path>", "file": "<path inside repo>", "evidence_span": "<verbatim excerpt>"}`.
   Same seam as incident_report, so agents learn one format. `answer.txt`
   cannot carry citations and **fails the gate outright**.
3. **Verification** — every span must appear in the cited file,
   whitespace-normalized and case-insensitive. Constants in
   `lib/eb_verify/groundedness.py`: `MIN_SPAN_CHARS = 20` (shorter spans =
   `too_short`), `MAX_EVIDENCE_FILE_BYTES = 10 MiB` (`too_large`, never
   read). Per-citation failure reasons: `ok`, `span_not_found`,
   `file_missing`, `path_escape` (workspace containment via
   `plugins.safe_read`), `too_short`, `too_large`. Any ungrounded citation ⇒
   artifact invalid.
4. **Capability probe** — `runner.py::validate_artifacts` forwards the flag
   only to validators whose `validate()` declares the
   `require_grounded_citations` kwarg; a required artifact whose validator
   can't enforce it **fails explicitly** rather than silently skipping the
   gate. Grounded-capable plugins today: `answer`, `incident_report`,
   `security_assessment` (`fact_triples` accepts the kwarg as a documented
   no-op). Pairing e.g. `code_patch` as required artifact with
   `require_grounded_citations = true` fails that artifact — don't.

Also restate the citation contract in your `instruction.md` (the two live
grounded tasks, `err-provenance-tri-httpx-socks-001` and
`err-provenance-tri-httpx-proxy-001`, both do; they are the reference
exemplars — only these 2 of 180 tasks opt in as of 2026-07-07).

## 7. Validation gates — what actually runs, and what is broken

### Local gates

```bash
# Schema-validate one task (needs `pip install -e lib/` or the checked-in venv)
python3 -m eb_verify validate benchmarks/<suite>/<task-id>/task.toml
# (the guide's `python3 -m lib.eb_verify validate …` form also works from repo root)

make verify-mix       # task_mix_validator.py — mix targets (§4); PASSES 2026-07-07
make verify-tasks     # validate_tasks_preflight.py — schema + structure; PASSES 2026-07-07
```

**`make verify` is currently broken at its third step** (verified
2026-07-07): `make verify-crnt` invokes
`scripts/validation/crnt_validator.py` with **no arguments**, but the script
requires a `task_toml` positional → argparse exits 2 and make stops. Same
bug in `make verify-expected-solutions` (missing required `path`). Until the
Makefile is fixed, run the underlying tools directly:

```bash
# CRNT, per task (exit 0 = pass or single-repo skip; exit 2 = fail)
python3 scripts/validation/crnt_validator.py benchmarks/<suite>/<task-id>/task.toml
# CRNT, all multi-repo tasks
find benchmarks -name task.toml -not -path "*/_archived/*" -not -path "*/mined/*" \
  -exec python3 scripts/validation/crnt_validator.py {} \;
# expected_solution.json, whole tree
python3 scripts/validation/validate_expected_solutions.py benchmarks/
```

CRNT pass condition (structural): the task declares ≥ 2 repos AND every
declared repo has at least one `ground_truth.required_files` entry. A
multi-repo task whose required_files all sit in one repo **fails CRNT** —
that usually means the task doesn't genuinely need the other repos; fix the
task, don't pad required_files. Empirical necessity (ablation runs) is
separate: `scripts/validation/verify_grounding.py`, and
`crnt_validator.py --output-dir` emits per-repo ablated configs. See
`eb-crnt-and-task-mix`.

### Preflight severity map (validate_tasks_preflight.py)

| Check                                                                                                                               | Severity                  |
| ----------------------------------------------------------------------------------------------------------------------------------- | ------------------------- |
| schema validation, missing instruction.md, missing/empty ground_truth.json, no checkpoints, weights ≠ 1.0, missing verifier scripts | **error** (fails the run) |
| non-executable scripts, missing environment/ or Dockerfile variants, missing mirror config, mirrors not indexed                     | warning                   |

Useful flags: `--suite <name>`, `--task-id <id>`, `--json`,
`--generate-registry` (writes `configs/validation_registry.json` — that one
mutates; don't run it casually).

### CI (the real merge bar — .github/workflows/ci.yml)

CI does **not** run `make verify`. It runs, in order:

1. `pip install -e lib/` then
   `pytest tests/ -v --tb=short -m "not network and not docker"` — this
   includes `tests/test_all_tasks_valid.py`, which re-validates every active
   task.toml against the schema, checks weights, scripts, ground_truth.json,
   instruction.md. Your task edit can fail CI here even if you never touched
   Python.
2. `python3 scripts/audit_consistency.py` — the verifier-hygiene audit (§3).
   **Trap (2026-07-07):** this script hardcodes
   `BENCH_DIR = Path("/home/ds/EnterpriseBench/benchmarks")` and raises
   `FileNotFoundError` when the repo lives anywhere else — it crashes at
   this working copy's path too. Treat its checks as the contract, run the
   individual checks via preflight/pytest until the path bug is fixed.
3. `bash -n` on every non-archived `benchmarks/**/*.sh`.

## 8. Runbook: add a new task

```bash
# 0. Pick suite + task_type (docs/TASK_TYPE_PRD.md) and stratum (§4).
#    Check the ecosystem cap BEFORE choosing repos:
python3 scripts/validation/task_mix_validator.py | tail -8

# 1. Scaffold the directory from the template
mkdir -p benchmarks/<suite>/<task-id>/checks
cp benchmarks/EXAMPLE_TASK.toml benchmarks/<suite>/<task-id>/task.toml
#    Edit: id (pattern ^[a-z][a-z0-9-]+-\d{3}$), suite, task_type, difficulty,
#    difficulty_stratum, mcp_suite="eb_v1", verification_modes, repos (pin revs),
#    checkpoints (weights sum to 1.0), artifacts, tool_access, ground_truth.

# 2. Write instruction.md — senior-engineer voice, states the deliverable and
#    output path (e.g. /workspace/<repo>/REPORT.md), never lists answer files.

# 3. Write ground_truth.json + [[ground_truth.required_files]] covering EVERY repo
#    (CRNT), then checks/check_<checkpoint_name>.sh per checkpoint (§3) and
#    chmod +x checks/*.sh

# 4. expected_solution.json (§5): scaffold, hand-curate, validate.

# 5. Gate locally, in this order:
python3 -m eb_verify validate benchmarks/<suite>/<task-id>/task.toml
python3 scripts/validate_tasks_preflight.py --task-id <task-id>
python3 scripts/validation/crnt_validator.py benchmarks/<suite>/<task-id>/task.toml
python3 scripts/validation/validate_expected_solutions.py benchmarks/<suite>/<task-id>
python3 scripts/validation/task_mix_validator.py
find benchmarks/<suite>/<task-id> -name "*.sh" -exec bash -n {} \;
python3 -m pytest tests/test_all_tasks_valid.py -q

# 6. Sandbox smoke-test before claiming the task works — eb-sandbox-execution.
```

### Pre-submit checklist

- [ ] task.toml passes schema + preflight with zero errors
- [ ] top-level `difficulty_stratum`, `mcp_suite`, `verification_modes` present, before any `[section]`
- [ ] weights sum to 1.0; every checkpoint file named `checks/check_<checkpoint_name>.sh`, executable, `set -euo pipefail`, JSON `score`+`passed` on stdout, diagnostics on stderr, `exit 0`
- [ ] no stray helper `.sh` files in `checks/` (production runs them all)
- [ ] every repo pinned (tag/SHA) and covered by ≥ 1 required_files entry (CRNT)
- [ ] expected_solution.json keys exactly match checkpoint names; no `_curation_required`
- [ ] `tool_access.expected_mcp_benefit` + rationale set
- [ ] mix targets still pass (`task_mix_validator.py`) — watch the go-ecosystem 40% cap
- [ ] no secrets; verifier scripts read env via `os.environ` in python blocks
- [ ] if grounded citations: required artifacts limited to grounded-capable validators; instruction.md restates the citation contract
- [ ] change-control: branch-ready + tests, maintainer sign-off for mix/repin/grading changes _(PROVISIONAL pending Stephanie)_

## Provenance and maintenance

Authored 2026-07-07 against the working tree at commit `7cfb8b0` (branch
state of the local checkout). Volatile facts and their one-line re-checks:

```bash
# Active task count (was 180) and per-stratum counts (§1, §4)
find benchmarks -name task.toml -not -path "*/_archived/*" -not -path "*/mined/*" | wc -l
find benchmarks -name task.toml -not -path "*/_archived/*" -not -path "*/mined/*" \
  -exec grep -m1 '^difficulty_stratum' {} \; | sort | uniq -c

# Schema enums (difficulty, strata, tiers, verification_modes, artifact types)
grep -n '"enum"' -A8 schemas/task.schema.json | less

# make verify-crnt / verify-expected-solutions still broken? (was: argparse exit 2)
make verify-crnt; make verify-expected-solutions

# Mix targets and current margins (was: go at 39.7% of the 40% cap)
python3 scripts/validation/task_mix_validator.py | tail -8

# audit_consistency.py hardcoded path still present? (was: crashes off /home/ds/EnterpriseBench)
grep -n 'BENCH_DIR' scripts/audit_consistency.py

# Production still ignores task.toml weights/timeouts? (.meta only in test_runner.sh)
grep -rn '\.meta' scripts/sandbox/test_runner.sh scripts/orchestration/run_task.py

# Grounded-citation opt-in count (was 2) and grounded-capable plugins (was answer,
# incident_report, security_assessment + fact_triples no-op)
grep -rln 'require_grounded_citations' --include='*.toml' benchmarks | grep -v _archived
grep -ln 'require_grounded_citations' lib/eb_verify/plugins/*.py

# expected_solution.json coverage (was 173/180)
find benchmarks -name expected_solution.json -not -path "*/_archived/*" -not -path "*/mined/*" | wc -l

# CI steps (was: pytest + audit_consistency + bash -n; no make verify, no lint)
cat .github/workflows/ci.yml

# Guide-vs-schema drift (difficulty 'easy', tiers vocabulary) still unfixed?
grep -n 'easy\|llm_curator|solve_verification' docs/TASK_AUTHORING_GUIDE.md
```

PROVISIONAL markers in this skill depend on discovery-report Q3 (two-scorer
future) and Q5 (unwritten gating; parked-not-dead) provisional positions,
plus Q1 (repo-portable placement) for its overall framing. Revise when
Stephanie's real answers land.
