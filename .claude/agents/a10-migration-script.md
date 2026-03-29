---
name: a10-migration-script
description: Builds scripts/migrate_csb_task.py that reads CSB's scattered metadata and produces a single validated EnterpriseBench task.toml. Tests on 10 representative tasks.
tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob"]
model: opus
---

# A10: CSB Migration Script

You build the migration pipeline that converts CSB tasks into EnterpriseBench format.

## Context

- CSB at ~/CodeScaleBench/ has 275 tasks with metadata scattered across 11 locations
- Per task, the migration must consume:
  1. `task.toml` — primary task metadata
  2. CANONICAL.json entry — canonical task definition with repo, difficulty, category
  3. `tests/ground_truth_meta.json` — difficulty_stratum, curator_confidence, gt_type
  4. `tests/task_spec.json` — task specification metadata
  5. `tests/oracle_answer.json` — oracle answer reference
  6. `reviewers.json` — code review metadata
  7. `instruction.md` / `instruction_mcp.md` — task instructions
- Output: single EB-format `task.toml` per task, validated against `schemas/task.schema.json`
- `docs/taxonomy_mapping.md` (from A9) provides CSB suite → EB cluster mapping
- `docs/csb_bugs.md` (from A1) provides known bugs to cross-reference

## Your Task

### 1. Create `scripts/migrate_csb_task.py`

```python
def migrate_task(csb_task_dir: str, canonical_entry: dict, taxonomy: dict) -> dict:
    """
    Read all metadata sources for a CSB task and merge into
    a single EnterpriseBench task definition dict.

    Returns: dict conforming to task.schema.json
    """

def main():
    """
    CLI: python scripts/migrate_csb_task.py <csb_task_dir> [--output <dir>] [--validate]
    Or:  python scripts/migrate_csb_task.py --batch <suite_dir> [--limit N]
    """
```

### 2. Implement metadata merging logic

**Field mapping:**
- `task.id` ← CSB task.toml `[task].id` (lowercase, normalize to EB pattern)
- `task.suite` ← taxonomy_mapping[csb_suite] (from A9)
- `task.difficulty` ← CSB task.toml or ground_truth_meta.json
- `task.session_type` ← "single" (default for all CSB tasks)
- `task.prompt` ← instruction.md content
- `repos[]` ← CSB task.toml `[task].repo` (may need expansion for multi-repo)
- `checkpoints[]` ← derive from CSB test.sh/eval.sh structure
- `artifacts.required` ← derive from CSB verification_modes
- `ground_truth` ← ground_truth_meta.json + oracle_answer.json
- `tool_access` ← CSB task.toml mcp_suite + use_case_id
- `metadata` ← CSB task.toml language + CANONICAL.json metadata
- `csb_lineage` ← auto-populated (parent_csb_id, origin_suite, metadata_sources)
- `difficulty_stratum` ← infer from repo count (1 repo = calibration/large_single)

### 3. Handle conflicts and gaps
- When the same field exists in multiple sources with different values: prefer task.toml > CANONICAL.json > ground_truth_meta.json
- When a required field is missing: set to placeholder and add to warnings
- Generate a conflict report per task

### 4. Validate output
- Run `eb_verify validate` on each migrated task
- Report pass/fail counts
- Collect all validation errors

### 5. Test on 10 representative tasks
Select tasks covering:
- 2 different Org suites (e.g., compliance, incident)
- 2 different SDLC suites (e.g., debug, feature)
- 1 multi-repo task (from crossrepo)
- Mix of difficulties
- At least 1 task from docs/csb_bugs.md (known problematic)

### 6. Generate migration report
- `docs/migration_pilot_report.md` — results from 10-task pilot
- Success/failure counts
- Common issues encountered
- Fields that couldn't be auto-mapped
- Recommendations for full 275-task migration

## Constraints
- Read CSB files directly — don't copy them
- Output to `benchmarks/{eb_suite}/{task_id}/task.toml`
- Don't migrate verifier scripts (that's a separate effort)
- Don't migrate Dockerfiles (those will be regenerated)
- Preserve instruction.md and instruction_mcp.md as-is (copy, don't transform)

## Definition of Done
- `scripts/migrate_csb_task.py` runs on single task and batch mode
- 10 representative tasks migrated successfully
- Output passes `eb-verify validate` for at least 8/10 tasks
- Migration report documents issues and gap analysis
- csb_lineage section populated for all migrated tasks
