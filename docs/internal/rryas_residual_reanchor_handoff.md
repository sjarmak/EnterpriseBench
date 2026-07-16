# Handoff: finish the report-verifier prompt-echo remediation (residual 11)

**Epic:** `EnterpriseBench-rryas` (clean MCP vs baseline vs CLI headline study).
**Parent:** `EnterpriseBench-jn73.2.7.3.1` (report-verifier prompt-echo standardize).
**This task:** clear the last 11 quarantined report tasks so the prompt-echo CI
invariant is fully enforced (quarantine → 0), then the pre-headline fidelity gate.

## What is already done (do not redo)

The prompt-echo root cause and the bulk fix are landed on `main`:

- **Root cause:** gen-1 report verifiers grade *concept vocabulary the prompt
  already hands the agent*, so `cp instruction.md <deliverable>` scored full
  credit. 46/47 curated leaks were concept greps. The gen-2 `scoring_evidence`
  discipline (dep-traversal, `vjrbw`) was never swept across families.
- **CI invariant (commit `a51e7e8`):** `tests/integrity/test_report_prompt_echo.py`
  enforces echo=0 on every tracked report deliverable; known leakers are
  quarantined strict-xfail in `tests/integrity/known_prompt_echo_leaks.json`
  (the list only shrinks). Fixing a task flips its xfail (XPASS→fail) → remove it.
- **67 tasks re-anchored** to `ground_truth.json:scoring_evidence` (commit
  `a51e7e8` = 42 tracked; commit `299977d` = 25 previously-untracked multi-repo
  tasks). Each verified echo=0 AND expected_solution passes every check.
- **Quarantine went 78 → 11.** The 11 below are what remain.

Tools you will reuse:
- `scripts/authoring/reanchor_report_checks.py <task_dir> [--apply|--json]` —
  mechanical migration (maps checks→checkpoints, extracts non-prompt evidence
  from expected_solution.json, swaps the check body to the scoring_evidence
  grep-grader, refuses below 2 non-prompt tokens/checkpoint).
- `scripts/validation/curated_gate_analyzer.py --rescan-quarantine` — rewrite the
  quarantine from a fresh echo scan (a reviewed act, run only after fixing tasks).
- Verify one task: `python3 -c "import sys;sys.path.insert(0,'scripts/validation');
  import curated_gate_analyzer as A,pathlib as P;print(A.echo_leak(P.Path('<dir>')))"`
  (empty dict = clean).

## The residual 11 — two DIFFERENT failure mechanisms

The bulk tool does not fit either class; both need per-task judgment.

### Class A — structured-deliverable / free-credit (7 tasks)

```
platform_engineering/config-drift-001, -002, -003, -004
platform_engineering/config-drift-dual-argocd-001, -dual-prometheus-001
incident_response/ansible-galaxy-tar-regression-prove-001
```

These grade a **JSON deliverable** (`charts/DRIFT_REPORT.json`, etc.) by parsing
fields, not by grep — so the scoring_evidence grep-grader does not apply. Worse,
the leak here is usually NOT concept-vocabulary: it is a **free-credit fallback**.
Example `config-drift-001/check_config_valid.sh`:

```bash
# No corrected config is optional — give partial credit for the report alone
printf '{"score": 1.0, "passed": true, "reason": "... optional checkpoint — skipped"}\n'
```

Any deliverable (including a prompt copy) scores 1.0 because the optional
corrected-config artifact is absent → auto-pass. Fix per check:
- An "optional" checkpoint must score **0 when unsatisfied**, never 1.0. Auto-1.0
  on a missing artifact is free credit; route to 0.0/false (or drop the
  checkpoint if it genuinely tests nothing).
- For the field-parsed checks, grade the parsed field values against
  `scoring_evidence` tokens (extend `reanchor_report_checks.py` with a
  JSON-deliverable grader, or follow the err-provenance answer.json pattern:
  compare identified files to `ground_truth.required_files`, which is already
  echo-resistant).

Each config-drift task has 3–4 checks; inspect all of them, not just the leaking
one — the free-credit pattern recurs.

### Class B — checkpoints grade prompt-provided info (4 tasks)

```
technical_debt/refactor-orchestration-005, -006, -tri-babel-001
feature_delivery/monorepo-boundary-003
```

Checkpoints like `identify_repos`, `topological_order`, `parallelism`,
`classify_change_impact` grade information the **prompt already gives** (the repo
set, the order of the listed repos). They cannot be made echo-resistant by
non-prompt evidence because the graded answer *is* prompt-derived — the tool
correctly refuses (only 1 non-prompt token per checkpoint). Three options, pick
per checkpoint:
1. **Re-scope to the non-prompt specifics** that a real investigation surfaces:
   for `topological_order`, the specific version bumps / PR numbers / `go.mod`
   edges that PROVE the order (not the repo names); for `identify_repos`, the
   dependency EDGE evidence (which module imports which) rather than the names.
   Requires reading the repos at the pinned SHA to curate real evidence.
2. **Move to LLM-judge scoring.** expected_solution.json already carries
   `evaluation_criteria` per checkpoint; a checkpoint that inherently tests a
   judgment (is the plan's ordering correct?) is a judge checkpoint, not a grep
   one. Document the exception.
3. **Re-weight / drop** a checkpoint that tests only prompt-given info and so
   measures nothing.

## Verification loop (per task)

1. Fix the checks (Class A: kill free-credit + field-grade; Class B: re-scope
   evidence or convert to judge).
2. Confirm `A.echo_leak(dir)` is empty AND the expected_solution, dropped in as
   the deliverable, still passes every check (internal consistency).
3. `--rescan-quarantine`; the fixed task drops out. Run
   `pytest tests/integrity/test_report_prompt_echo.py -q` → the task moves from
   xfail to enforced-green.
4. Ship the test change in the same commit as the verifier change.

## Pre-headline gate (P0, do before any run)

Path fidelity of the anchored evidence was NOT verified (no `GITHUB_TOKEN` in the
fix session). The 67 re-anchored tasks grade `scoring_evidence` tokens sourced
from expected_solution.json, which has known answer-key fidelity bugs (see the
answer-key-fidelity beads `c7iik`, `behb8`). Before the headline run:

- `GITHUB_TOKEN=... python3 scripts/validation/validate_expected_solutions.py
  benchmarks/ --check-paths` — confirm every anchored path resolves at the pinned
  SHA. A path that 404s makes its checkpoint un-passable by a correct agent.
- Reconcile `incident-investigation-dual-flux-001`: its `ground_truth.expected_answer`
  cites different files than the scoring_evidence I anchored (the only detected
  contradiction). Verify against helm-controller / flux2 source at the pinned SHA
  and correct whichever key is wrong.

## Also note (not blocking)

- 9 prose checkpoints (mostly `remediation_proposal`) use **pooled** file-path
  evidence — echo-resistant but not checkpoint-unique (a report citing the
  affected files passes without proposing a fix). Candidates for judge-scoring.
  Grep the re-anchored ground_truth for repeated path sets to find them.
- 64 report tasks in the tree are still untracked (pre-existing authoring beyond
  the 25 committed here). They are echo-clean in the working tree but absent from
  CI; commit or discard them as a separate concern before locking the curated set.

## Definition of done

`known_prompt_echo_leaks.json` empty (or only documented judge-scored
exceptions), `test_report_prompt_echo.py` fully enforced, path-fidelity gate
green, flux reconciled. Then rryas.8 curated selection resumes with an
echo-clean corpus.

## Pointers

- Root cause + gate analysis: `results/rryas_dataset/FINDINGS.md`
- Migration tool: `scripts/authoring/reanchor_report_checks.py`
- Invariant + quarantine: `tests/integrity/test_report_prompt_echo.py`,
  `tests/integrity/known_prompt_echo_leaks.json`
- Gen-2 template to mirror: `benchmarks/dependency_management/dep-traversal-004/checks/check_cve_id.sh`
- Curated-selection parent handoff: `docs/internal/rryas_curated_dataset_handoff.md`
