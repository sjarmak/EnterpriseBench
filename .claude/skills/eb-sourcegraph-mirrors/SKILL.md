---
name: eb-sourcegraph-mirrors
description: >
  Provisioning and tracking sg-evals Sourcegraph mirrors for EnterpriseBench.
  Load this when you: create or rename an sg-evals mirror; add a repo/rev to a
  task and need its mirror provisioned; touch scripts/infra/mirror_naming.py,
  scripts/infra/create_sg_mirrors.py, scripts/generate_sg_index.py,
  scripts/infra/verify_sg_indexing.py, configs/sg_mirrors/*.json, or
  configs/sg_indexing_list.json; see the preflight warning "Not all mirrors
  indexed in sg_indexing_list"; wonder why verify_sg_indexing reports 0
  indexed; hit a malformed mirror name (sg-evals/sg-evals/*, org embedded,
  "<sha>~1" rev); or need to know how mirror names reach the agent's MCP
  repo filter. NOT for MCP endpoint config, tokens, or the run-time MCP
  pre-flight gate (use eb-mcp-modes) and NOT for writing task.toml files
  (use eb-task-authoring).
---

# eb-sourcegraph-mirrors: the sg-evals mirror model

Every repo a task uses is pinned to an exact rev (SHA or tag). For the MCP
arms of the benchmark (`mcp_only`, `hybrid`), the agent searches that exact
code on a Sourcegraph instance. Sourcegraph indexes moving branches, not
arbitrary pinned SHAs of upstream repos, so EnterpriseBench snapshots each
`repo@rev` into its own single-commit GitHub repo under the **sg-evals org**
and points Sourcegraph at those. These snapshots are the **mirrors**. This
skill covers how mirrors are named, created, indexed (tracked), and validated.

When NOT to use this skill:

| You are doing                                                                                                                         | Use instead            |
| ------------------------------------------------------------------------------------------------------------------------------------- | ---------------------- |
| Configuring the MCP endpoint, `.mcp.json`, `SOURCEGRAPH_ACCESS_TOKEN`, the run-time MCP pre-flight hard gate, 0-MCP-call invalidation | `eb-mcp-modes`         |
| Writing/fixing a `task.toml`, checkpoints, ground truth                                                                               | `eb-task-authoring`    |
| Docker build, clone-into-`/workspace/`, image tags                                                                                    | `eb-sandbox-execution` |
| Getting the test suite green the way CI runs it                                                                                       | `eb-build-and-test`    |
| First contact with the repo                                                                                                           | `eb-orientation`       |

## Vocabulary (defined once)

| Term                        | Meaning                                                                                                                                                                                                                                   |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **mirror**                  | A public GitHub repo under the `sg-evals` org holding one squashed snapshot of `upstream@rev` (single commit on `main`, no history)                                                                                                       |
| **sg-evals**                | The GitHub org that hosts all mirrors. Constant `ORG = "sg-evals"` in `scripts/infra/mirror_naming.py`                                                                                                                                    |
| **mirror name / `sg_name`** | `sg-evals/{repo}--{ref_suffix}`, e.g. `sg-evals/ansible--v2.16.0`. Derived ONLY by `derive_mirror_name()`                                                                                                                                 |
| **mirror file**             | `configs/sg_mirrors/<task_id>.json`: the per-task list of `{repo, rev, mirror_id}` (114 files as of 2026-07-07)                                                                                                                           |
| **`mirror_id`**             | The key inside mirror files and `tool_access.sourcegraph_mirrors[]`. Keeps the upstream org (`ansible/ansible--v2.16.0`); the real mirror name drops it. Do not confuse the two                                                           |
| **the index**               | `configs/sg_indexing_list.json`: the generated, checked-in roster of all unique mirrors (133 repos as of 2026-07-07) with `sg_name`, `github_repo`, `commit`, `_language`, `_loc_estimate`, `_tier`, `_indexed`, `_task_count`, `_suites` |
| **`_indexed`**              | Per-repo boolean in the index meaning "verified indexed on the Sourcegraph instance". Currently hardcoded `False` for every repo (see the gotcha section)                                                                                 |
| **preflight**               | `scripts/validate_tasks_preflight.py` (= `make verify-tasks`), whose check #10 is `mirrors_indexed`                                                                                                                                       |

## 1. The naming SSOT: `scripts/infra/mirror_naming.py`

One formula, one home. `derive_mirror_name(repo_url_or_path, rev)` returns
the full mirror name. It previously lived inline in `create_sg_mirrors.py`
and had drifted into 5 independent copies; the drift produced an index whose
`sg_name` was wrong for all 133 entries (org embedded:
`sg-evals/{org}/{repo}--{rev}` instead of `sg-evals/{repo}--{rev}`). Fixed by
extraction in commit `09a125f` (bead EnterpriseBench-k9po, 2026-07-05).
**Never re-implement or hand-compute the formula. Import it.**

The formula, in order:

1. Strip `https://` / `http://`, trailing `/`, trailing `.git` from the URL.
2. Keep only the last path segment: **the upstream org is dropped**
   (`github.com/ansible/ansible` -> `ansible`).
3. `ref_suffix` = first 8 chars of `rev` if `rev` is all-hex (a raw hash),
   else `rev` unchanged (a tag/branch). Then `/` -> `_`.
4. Result: `sg-evals/{repo_name}--{ref_suffix}`.

Worked examples (each is a test in `tests/test_mirror_naming.py`, and the
GitHub names were verified live against the sg-evals org when the tests were
written):

| Input repo                         | Input rev                                  | Mirror name                              |
| ---------------------------------- | ------------------------------------------ | ---------------------------------------- |
| `github.com/ansible/ansible`       | `v2.16.0`                                  | `sg-evals/ansible--v2.16.0`              |
| `github.com/LibreOffice/core`      | `61f8fb648ecf9a20ee8abec0e8d3fad3e666db5e` | `sg-evals/core--61f8fb64`                |
| `github.com/apache/gecko-dev`      | `releases/gecko-1.2`                       | `sg-evals/gecko-dev--releases_gecko-1.2` |
| `github.com/dandydeveloper/charts` | `redis-ha-4.26.6`                          | `sg-evals/charts--redis-ha-4.26.6`       |
| `github.com/bitnami/charts`        | `130ffd163382...` (full SHA)               | `sg-evals/charts--130ffd16`              |

Consequences you must respect:

- **Full SHAs truncate to 8 chars** even if a mirror file stored the full
  40-char SHA (regression: `support-map-libreoffice-formula-007`).
- **The `<sha>~1` trap.** Git parent notation (`abc123~1`) is not all-hex, so
  `is_hex_rev()` classifies it as a tag and it lands verbatim in the name.
  `~` is illegal in GitHub repo names, so the mirror is unrepresentable and
  creation fails. Five mirror files once pinned such revs (bead k9po).
  **Resolve to a concrete SHA first** (`git rev-parse 'abc123~1'` in a clone,
  or `gh api repos/{org}/{repo}/commits/{ref} --jq .sha`), then use that SHA.
- **Legality gate:** `GITHUB_REPO_NAME_RE` in `mirror_naming.py` is the same
  validation `create_sg_mirrors.py` applies before creating anything. A name
  that fails it (e.g. contains `~`) is a bug in your rev, not in the regex.
- **Org-collision caveat:** because the upstream org is dropped, two repos
  with the same name are distinguished only by rev. `bitnami/charts` and
  `dandydeveloper/charts` coexist today because their revs differ. Same name
  AND same rev string from different orgs would collide. No guard exists for
  this; check the index before adding a same-named repo.

### Who consumes the formula (all import `mirror_naming`; verified 2026-07-07)

| Call site                                                          | What it does with the name                                                                                                                                                            |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `scripts/infra/create_sg_mirrors.py`                               | Names the GitHub repos it creates                                                                                                                                                     |
| `scripts/generate_sg_index.py`                                     | Derives every `sg_name` in the index                                                                                                                                                  |
| `scripts/validate_tasks_preflight.py`                              | Matches task mirrors against the index (check #10)                                                                                                                                    |
| `scripts/sandbox/dockerfile_generator.py` (`mirror_name_for_repo`) | Builds the `git clone https://github.com/sg-evals/{name}.git` line in generated Dockerfiles (default `--source mirror`) and the `SOURCEGRAPH_REPO_NAME`/`SOURCEGRAPH_REPOS` env value |
| `agents/harnesses/claude/mcp/sourcegraph.py` (`_build_repo_scope`) | Emits the agent's MCP search filter: `repo:^github.com/sg-evals/{name}$`                                                                                                              |
| `scripts/infra/generate_mcp_instructions.py`                       | Writes the same mirror names into `instruction_mcp.md` / `.mcp.json` (via `dockerfile_generator.mirror_name_for_repo`)                                                                |

This table is why the name is load-bearing three separate ways: the sandbox
clones from it, the agent's search filter is scoped to it, and the preflight
validates against it. A drifted name breaks silently at whichever consumer
you didn't test.

## 2. The artifact chain

```
task.toml [[repos]] (url + rev)
    |            \
    |             `--> configs/sg_mirrors/<task_id>.json   (per-task mirror file)
    v
scripts/infra/create_sg_mirrors.py  ->  configs/runs/mirror_creation_manifest.json
    |  (--execute)                       (the manifest; 47K, generated)
    v
GitHub: sg-evals/{repo}--{ref}      (one snapshot repo per unique repo@rev)
    |
    | (Sourcegraph instance indexes the sg-evals org -- external, manual)
    v
scripts/generate_sg_index.py        ->  configs/sg_indexing_list.json (checked in)
    |
    v
scripts/validate_tasks_preflight.py     check #10 "mirrors_indexed" (warning)
scripts/infra/verify_sg_indexing.py     status report (0/133 indexed today; see gotcha)
```

Mirror file format (`configs/sg_mirrors/ansible-galaxy-tar-regression-prove-001.json`):

```json
{
  "task_id": "ansible-galaxy-tar-regression-prove-001",
  "mirrors": [
    {
      "repo": "github.com/ansible/ansible",
      "rev": "v2.16.0",
      "mirror_id": "ansible/ansible--v2.16.0"
    }
  ]
}
```

Note `mirror_id` keeps the upstream org. `generate_sg_index.py` deliberately
derives `sg_name` from `repo` + `rev` via `derive_mirror_name()`, NOT from
`mirror_id`, and sorts by the derived value (see the comment at
`scripts/generate_sg_index.py:317`).

Stale-doc warning: the docstring at the top of `create_sg_mirrors.py`
mentions a `--manifest-only` flag. It does not exist; `--help` shows only
`--execute`, `--dry-run`, `--no-skip`, `--output`. Manifest-only is the
default when you omit `--execute`. Also, `configs/mirror_creation_manifest.json`
(5.1K, repo root of `configs/`) is an older artifact; the script's default
output is `configs/runs/mirror_creation_manifest.json`.

## 3. Runbooks

All commands run from the repo root. `python3` suffices for these scripts
(stdlib + tomllib); the preflight additionally wants `jsonschema`, so prefer
the project venv (`pip install -e lib/` environment) where available.

### 3a. Provision mirrors for a new or changed task

```bash
# 1. Preview what would be created (manifest only, no network writes)
python3 scripts/infra/create_sg_mirrors.py benchmarks/<suite>/<task_id>/task.toml

# 2. Dry-run the creation (checks name legality, resolves short hashes)
python3 scripts/infra/create_sg_mirrors.py benchmarks/<suite>/<task_id>/task.toml --execute --dry-run

# 3. Create for real (requires gh CLI authenticated with sg-evals org access)
python3 scripts/infra/create_sg_mirrors.py benchmarks/<suite>/<task_id>/task.toml --execute
```

Step 3 is an EXTERNAL, mutating action (creates public GitHub repos, can
delete-and-recreate empty ones). Treat it like any external artifact: get
explicit approval before running it. What `--execute` does per mirror:
create repo, disable secret scanning (OSS fixtures trip push protection),
download the upstream tarball at the resolved ref, `git init` + single
commit as `sg-evals <benchmarks@sourcegraph.com>`, push `main`. On GH013
push-protection rejection it retries via a private->push->public toggle.
Existing non-empty mirrors are skipped (idempotent); `--no-skip` retries
empty/failed ones. Rate limiting: 5s sleep per creation, 60s backoff on
"too quickly" errors.

Then:

```bash
# 4. Write/refresh the per-task mirror file (hand-written today; match the
#    format in section 2, one entry per [[repos]] with the exact rev)
$EDITOR configs/sg_mirrors/<task_id>.json

# 5. Regenerate the index and confirm your repos appear
python3 scripts/generate_sg_index.py
git diff configs/sg_indexing_list.json

# 6. Run the tests that police this exact surface
venv/bin/python -m pytest tests/test_mirror_naming.py tests/test_sg_indexing_list.py tests/test_validate_tasks_preflight.py -q

# 7. Preflight the task
venv/bin/python scripts/validate_tasks_preflight.py --task-id <task_id>
```

There is no automation that writes `configs/sg_mirrors/*.json` from
task.toml (verified 2026-07-07: `generate_sg_index.py` only reads them;
`create_sg_mirrors.py` writes the manifest, not mirror files). Write the
mirror file by hand and let the tests catch drift:
`tests/test_sg_indexing_list.py::test_all_mirror_repos_in_index` and
`test_sg_name_matches_derivation` fail if the index and mirror files disagree.

### 3b. Regenerate the index

```bash
python3 scripts/generate_sg_index.py            # writes configs/sg_indexing_list.json
python3 scripts/generate_sg_index.py -o /tmp/x.json   # tests use this to avoid clobbering
```

Regeneration is idempotent modulo the `_generated` date (verified 2026-07-07
by regenerating to a scratch path and diffing: identical except `_generated`).
If your regen produces other diffs you didn't intend, you changed an input
(mirror files, benchmarks tree) or hit the backfill mechanism:

**BACKFILLED_SUITES:** `customer_escalation` and `platform_engineering`
entries in the `suites` section are carried over VERBATIM from the checked-in
index, not derived. They were hand-backfilled (commit `fa876ae`) from
task.tomls that exist only on unmerged branches. The generator fails loudly
if the checked-in index or either suite is missing, and raises if a
backfilled suite ever becomes derivable (the retire signal). Do not "fix"
those suites by editing the JSON; the generator will preserve whatever is
checked in. The per-repo `repos` array is always fully derived.

Also derived-not-editable: `_language` and `_loc_estimate` come from the
`LANGUAGE_HINTS` / `LOC_HINTS` dicts inside `generate_sg_index.py` (every
repo must have a language entry; LOC is an order-of-magnitude estimate that
feeds `_tier`: A > 500K, B 100K-500K, C < 100K). New repo => add it to both
dicts in the script, then regenerate. Never hand-edit the JSON.

### 3c. Check indexing status

```bash
python3 scripts/infra/verify_sg_indexing.py          # human-readable
python3 scripts/infra/verify_sg_indexing.py --json   # machine-readable
```

As of 2026-07-07 this prints `Total repos: 133, Indexed: 0, Pending: 133`.
That is NOT an outage. Read the next section before reacting.

## 4. The `_indexed`-hardcoded-False gotcha

`scripts/generate_sg_index.py:346` sets `entry["_indexed"] = False` for
**every** repo, unconditionally. Nothing on `main` ever sets it true:
`verify_sg_indexing.py --check-api` (the thing that would query the live
Sourcegraph instance) is an explicit stub (`check_api_stub()`, "not yet
implemented"). The deferred implementation is tracked as bead
EnterpriseBench-k9po.1 (cited in the `validate_tasks_preflight.py` comment at
line 151 and in commit `09a125f`).

Consequences, all by design (do not "fix" them ad hoc):

1. `verify_sg_indexing.py` reports 0 indexed / all pending, forever, until
   `--check-api` lands.
2. Preflight check #10 (`mirrors_indexed`) WARNS for every task that declares
   `tool_access.sourcegraph_mirrors[]`. The warning "Not all mirrors indexed
   in sg_indexing_list" on such tasks is ambient noise today, not a
   regression signal. It is severity `warning`, so it never blocks: the task
   still counts as `ready` and `make verify-tasks` still exits 0.
3. Nothing at run time verifies per-repo indexing either. The MCP pre-flight
   hard gate in `run_task.py::_configure_mcp` checks endpoint reachability,
   auth, and the Claude handshake, NOT that your task's mirrors are indexed
   (that gate is eb-mcp-modes territory). If a mirror is missing or unindexed
   on the Sourcegraph instance, the agent's scoped searches
   (`repo:^github.com/sg-evals/{name}$`) return nothing and the `mcp_only`
   arm degrades silently. This is the gap `_indexed` + `--check-api` is meant
   to close. Until then, the only verification is manual: search the mirror
   on the Sourcegraph instance before trusting an `mcp_only` run of a new task.

PROVISIONAL pending Stephanie (Q5, parked-not-dead): a real `--check-api`
implementation exists on unmerged history (commit `82aff10` reachable from
branch `fix/eb-5eq9-preserve-branch-triage`; a related `e865b78` is not on
any local branch). Per the campaign's provisional ruling, treat these as
parked, not dead: before implementing `--check-api` yourself, check the bead
store (k9po.1) and those branches so you don't duplicate an unlanded fix.

### The two match semantics inside preflight check #10

`validate_tasks_preflight.py` deliberately uses different predicates for its
two data sources (unified in commit `a3e641d`, on `main`):

| Source of mirror claims                          | Predicate                  | Semantics                                 | Outcome today (all `_indexed` False)                                                                        |
| ------------------------------------------------ | -------------------------- | ----------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `tool_access.sourcegraph_mirrors[]` in task.toml | `_mirror_verified_indexed` | name present in index AND `_indexed` true | `mirrors_indexed=False` + warning (verified live on `ccx-dep-trace-106`, 2026-07-07)                        |
| `configs/sg_mirrors/<task_id>.json` fallback     | `_mirror_present_in_index` | name present in index, `_indexed` ignored | `mirrors_indexed=True`, no warning (verified live on `ansible-galaxy-tar-regression-prove-001`, 2026-07-07) |

So a task can flip its `mirrors_indexed` status just by moving where it
declares mirrors. That asymmetry is documented in the code (lines 138-156)
as intentional: the toml path wants verified-on-Sourcegraph semantics, the
config-file path wants presence-in-index. When `--check-api` lands and
`_indexed` becomes a real signal, the code comment says to revisit whether
the config-file path should switch to verified semantics too.

Two more edges of check #10, verified in code and tests:

- **Malformed `mirror_id` is flagged distinctly.** The toml path has no
  independent rev, so it strips the org off `mirror_id` and validates the
  remainder against `GITHUB_REPO_NAME_RE`. A never-transformed rev (e.g.
  `org/repo--rel/2.14.1` with the slash intact) gets a specific "not a legal
  sg-evals mirror name segment" warning instead of blending into "not
  indexed" (test: `test_malformed_mirror_id_flagged_distinctly_from_not_indexed`).
- **The config-file fallback sets `mirrors_indexed=False` silently** (no
  warning issue emitted) when a mirror is absent from the index, on `main`
  today. A fix adding the warning is parked on unmerged branch
  `EnterpriseBench-s7oe` (commit `b74bff0`). PROVISIONAL pending Stephanie
  (Q5): parked-not-dead; check the bead store before re-implementing.

## 5. Gotcha table (quick reference)

| Symptom                                                                                    | Cause                                                                          | Fix                                                                                                                 |
| ------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------- |
| `Invalid mirror name: ...~1...` or GitHub rejects repo creation                            | `<sha>~1` parent notation in a rev                                             | Resolve to a concrete SHA first, put the SHA in task.toml and the mirror file                                       |
| Index `sg_name` has two path segments after `sg-evals/`                                    | Formula bypassed; org embedded                                                 | Regenerate with `generate_sg_index.py`; never hand-edit `sg_name`                                                   |
| `verify_sg_indexing.py` shows 0 indexed                                                    | `_indexed` hardcoded False; `--check-api` is a stub                            | Expected. See section 4; do not hand-edit `_indexed` to true                                                        |
| Preflight warns "Not all mirrors indexed" on a task with `tool_access.sourcegraph_mirrors` | Verified-indexed semantics + `_indexed` always False                           | Ambient today (warning, non-blocking). Confirm the names are legal and present in the index; ignore the indexed bit |
| Regen diff touches `customer_escalation`/`platform_engineering` suites unexpectedly        | BACKFILLED_SUITES carryover                                                    | Those suite entries mirror the checked-in file; see section 3b                                                      |
| MCP searches return nothing for one repo in `mcp_only`                                     | Mirror missing/unindexed on the Sourcegraph instance; no automated gate exists | Manually verify the mirror on the instance; check the sg-evals org has the repo                                     |
| Full SHA in mirror file but 8-char name on GitHub                                          | Truncation is part of the formula                                              | Names always come from `derive_mirror_name()`; the stored rev may stay full                                         |
| Same-named repo from a different org                                                       | Org is dropped from names                                                      | Check the index for `{name}--{rev}` collisions before provisioning                                                  |

## 6. Change control

Mirror names, the index, and the preflight sit upstream of the `mcp_only`
measurement arm. PROVISIONAL pending Stephanie (Q5, conservative gating):
treat changes to `mirror_naming.py` semantics, mirror repins (rev changes),
and any weakening of preflight check #10 as requiring maintainer sign-off,
the same as production-scoring-path changes. Mechanical additions (new task's
mirror file + index regen) are normal task-authoring flow through
`make verify`. Tests ship in the same commit; the policing tests are
`tests/test_mirror_naming.py`, `tests/test_sg_indexing_list.py`, and the
mirror sections of `tests/test_validate_tasks_preflight.py` (41 tests in the
first two, all passing 2026-07-07). CI (`.github/workflows/ci.yml`) runs the
whole `tests/` tree, so these gate merges.

## Provenance and maintenance

Authored 2026-07-07 against `main` @ `7cfb8b0` (working copy
`sjarmak/EnterpriseBench`). Every command above was executed read-only this
session except step 3 of runbook 3a (mirror creation), which is documented
from code, its `--help`, and commit history, and was NOT executed (external,
mutating). Live sg-evals GitHub org contents and Sourcegraph instance state
were NOT verified this session (network); the worked-example names rest on
the k9po/p6ms regression tests, which record live verification at fix time.

Volatile facts and how to re-verify each:

```bash
# Counts (133 repos / 114 mirror files / 0 indexed as of 2026-07-07)
python3 scripts/infra/verify_sg_indexing.py | head -6
ls configs/sg_mirrors/*.json | wc -l

# _indexed still hardcoded False in the generator
grep -n '_indexed.*= False' scripts/generate_sg_index.py

# --check-api still a stub on main
grep -n "check_api_stub\|not yet implemented" scripts/infra/verify_sg_indexing.py

# The two preflight predicates still split (verified vs presence)
grep -n "_mirror_verified_indexed\|_mirror_present_in_index" scripts/validate_tasks_preflight.py

# BACKFILLED_SUITES still active (delete section 3b's caveat when empty)
grep -n "BACKFILLED_SUITES = " scripts/generate_sg_index.py

# SSOT consumers unchanged (expect the 6 call sites from section 1's table)
grep -rln "from mirror_naming import\|import mirror_naming" scripts agents --include='*.py'

# Index regeneration still idempotent (expect: only _generated differs)
python3 scripts/generate_sg_index.py -o /tmp/sg_regen.json && diff <(grep -v _generated configs/sg_indexing_list.json) <(grep -v _generated /tmp/sg_regen.json)

# Naming/index/preflight tests still green
venv/bin/python -m pytest tests/test_mirror_naming.py tests/test_sg_indexing_list.py -q

# Parked branches still unmerged (check-api: 82aff10; fallback warning: b74bff0)
git branch --all --contains 82aff10; git branch --all --contains b74bff0

# create_sg_mirrors flags (docstring's --manifest-only is stale; confirm before trusting)
python3 scripts/infra/create_sg_mirrors.py --help
```
